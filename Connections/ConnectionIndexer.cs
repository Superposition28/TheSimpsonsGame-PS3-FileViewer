using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.Data.Sqlite;
using TheSimpsonsGame.FileViewer.Formats;
using TheSimpsonsGame.FileViewer.IO;

namespace TheSimpsonsGame.FileViewer.Connections;

public class ConnectionIndexer
{
    private readonly string _databasePath;
    private readonly string _sourceRoot;
    private readonly List<string> _extractedRoots;
    private readonly int _maxParseBytes;

    public ConnectionIndexer(string databasePath, string sourceRoot, List<string> extractedRoots, int maxParseBytes = 32 * 1024 * 1024)
    {
        _databasePath = databasePath;
        _sourceRoot = sourceRoot;
        _extractedRoots = extractedRoots;
        _maxParseBytes = maxParseBytes;
    }

    public Dictionary<string, object> Build(Action<string>? progress = null)
    {
        var startTime = DateTime.UtcNow;
        string? dir = Path.GetDirectoryName(_databasePath);
        if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);

        if (File.Exists(_databasePath)) File.Delete(_databasePath);

        using var db = new SqliteConnection($"Data Source={_databasePath}");
        db.Open();

        using (var pragmaCmd = db.CreateCommand())
        {
            pragmaCmd.CommandText = "PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;";
            pragmaCmd.ExecuteNonQuery();
        }

        using (var schemaCmd = db.CreateCommand())
        {
            schemaCmd.CommandText = @"
CREATE TABLE files(id INTEGER PRIMARY KEY, view TEXT, root TEXT, path TEXT, level TEXT,
 format TEXT, size INTEGER, sha256 TEXT, archive INTEGER, member TEXT, locator TEXT,
 status TEXT, language TEXT);
CREATE TABLE ids(id INTEGER PRIMARY KEY, file INTEGER, namespace TEXT, value TEXT,
 role TEXT, offset INTEGER, width INTEGER, endian TEXT, label TEXT, confidence TEXT,
 doc TEXT, region TEXT);
CREATE TABLE edges(id INTEGER PRIMARY KEY, source INTEGER, target INTEGER, kind TEXT,
 label TEXT, confidence TEXT);
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
CREATE INDEX file_hash ON files(sha256);
CREATE INDEX file_level ON files(level,view);
CREATE INDEX file_archive ON files(archive);
CREATE INDEX id_file ON ids(file,role);
CREATE INDEX id_key ON ids(namespace,value,role);
CREATE INDEX id_value ON ids(value,role);
CREATE INDEX edge_source ON edges(source);
CREATE INDEX edge_target ON edges(target);";
            schemaCmd.ExecuteNonQuery();
        }

        progress?.Invoke("Scanning source files...");
        var originalFileIdsBySha = new Dictionary<string, List<long>>(StringComparer.OrdinalIgnoreCase);

        // 1. Scan source directory
        if (Directory.Exists(_sourceRoot))
        {
            var files = Directory.GetFiles(_sourceRoot, "*.*", SearchOption.AllDirectories)
                .Where(f => !f.Contains(".history") && !f.Contains(".backup") && !f.Contains(".git"))
                .ToList();

            using var tx = db.BeginTransaction();
            foreach (var file in files)
            {
                string relPath = Path.GetRelativePath(_sourceRoot, file).Replace('\\', '/');
                string ext = Path.GetExtension(file).ToLowerInvariant();
                long size = new FileInfo(file).Length;
                string level = InferLevel(relPath);

                if (ext == ".str")
                {
                    IndexStrArchive(db, file, relPath, level, originalFileIdsBySha);
                }
                else
                {
                    IndexStandaloneFile(db, _sourceRoot, relPath, file, level, "original file", originalFileIdsBySha);
                }
            }
            tx.Commit();
        }

        // 2. Scan extracted roots and build provenance edges
        foreach (var extractedRoot in _extractedRoots)
        {
            if (!Directory.Exists(extractedRoot)) continue;
            progress?.Invoke($"Scanning extracted root: {Path.GetFileName(extractedRoot)}...");

            var files = Directory.GetFiles(extractedRoot, "*.*", SearchOption.AllDirectories)
                .Where(f => !f.Contains(".history") && !f.Contains(".backup") && !f.Contains(".git"))
                .ToList();

            using var tx = db.BeginTransaction();
            foreach (var file in files)
            {
                string relPath = Path.GetRelativePath(extractedRoot, file).Replace('\\', '/');
                string level = InferLevel(relPath);
                string sha = ComputeSha256(file);
                long size = new FileInfo(file).Length;
                string format = FormatDetector.Identify(relPath);

                long fileId;
                using (var ins = db.CreateCommand())
                {
                    ins.CommandText = @"
INSERT INTO files(view, root, path, level, format, size, sha256, archive, member, locator, status, language)
VALUES('extracted', @root, @path, @level, @format, @size, @sha256, NULL, NULL, '{}', 'extracted file', 'ANY');
SELECT last_insert_rowid();";
                    ins.Parameters.AddWithValue("@root", extractedRoot);
                    ins.Parameters.AddWithValue("@path", relPath);
                    ins.Parameters.AddWithValue("@level", level);
                    ins.Parameters.AddWithValue("@format", format);
                    ins.Parameters.AddWithValue("@size", size);
                    ins.Parameters.AddWithValue("@sha256", sha);
                    fileId = Convert.ToInt64(ins.ExecuteScalar());
                }

                // If sha matches an original file/member, create provenance edge
                if (originalFileIdsBySha.TryGetValue(sha, out var origIds))
                {
                    foreach (var origId in origIds)
                    {
                        using var edgeCmd = db.CreateCommand();
                        edgeCmd.CommandText = "INSERT INTO edges(source, target, kind, label, confidence) VALUES(@src, @tgt, 'extracted copy', 'SHA-256 identical original payload', 'provenance')";
                        edgeCmd.Parameters.AddWithValue("@src", origId);
                        edgeCmd.Parameters.AddWithValue("@tgt", fileId);
                        edgeCmd.ExecuteNonQuery();
                    }
                }
            }
            tx.Commit();
        }

        // Summary
        long totalFiles = 0, totalIds = 0, totalEdges = 0;
        using (var c = db.CreateCommand()) { c.CommandText = "SELECT COUNT(*) FROM files"; totalFiles = Convert.ToInt64(c.ExecuteScalar()); }
        using (var c = db.CreateCommand()) { c.CommandText = "SELECT COUNT(*) FROM ids"; totalIds = Convert.ToInt64(c.ExecuteScalar()); }
        using (var c = db.CreateCommand()) { c.CommandText = "SELECT COUNT(*) FROM edges"; totalEdges = Convert.ToInt64(c.ExecuteScalar()); }

        var summary = new Dictionary<string, object>
        {
            ["built_at"] = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ"),
            ["source"] = _sourceRoot,
            ["extracted"] = _extractedRoots,
            ["seconds"] = Math.Round((DateTime.UtcNow - startTime).TotalSeconds, 2),
            ["files"] = totalFiles,
            ["identifiers"] = totalIds,
            ["provenance_edges"] = totalEdges,
            ["resolution"] = "same archive, same level, compatible language, nearest semantic path"
        };

        using (var metaCmd = db.CreateCommand())
        {
            metaCmd.CommandText = "INSERT INTO meta VALUES('summary', @summary)";
            metaCmd.Parameters.AddWithValue("@summary", JsonSerializer.Serialize(summary));
            metaCmd.ExecuteNonQuery();
        }

        return summary;
    }

    private void IndexStrArchive(SqliteConnection db, string archiveFullPath, string relPath, string level, Dictionary<string, List<long>> shaMap)
    {
        long archiveId;
        long archiveSize = new FileInfo(archiveFullPath).Length;
        using (var ins = db.CreateCommand())
        {
            ins.CommandText = @"
INSERT INTO files(view, root, path, level, format, size, sha256, archive, member, locator, status, language)
VALUES('source', @root, @path, @level, '.str', @size, '', NULL, NULL, '{}', 'original archive', 'ANY');
SELECT last_insert_rowid();";
            ins.Parameters.AddWithValue("@root", _sourceRoot);
            ins.Parameters.AddWithValue("@path", relPath);
            ins.Parameters.AddWithValue("@level", level);
            ins.Parameters.AddWithValue("@size", archiveSize);
            archiveId = Convert.ToInt64(ins.ExecuteScalar());
        }

        try
        {
            var str = StrArchive.Load(archiveFullPath);
            foreach (var section in str.Sections)
            {
                foreach (var chunk in section.Chunks)
                {
                    if (chunk.ChunkType == 0x1607) // Embedded Asset
                    {
                        string memberName = chunk.FileName;
                        string memberPath = chunk.FullPath;
                        string format = FormatDetector.Identify(memberPath, chunk.ResourceType, chunk.PayloadData);
                        string sha = ComputeSha256(chunk.PayloadData);

                        var locator = new Dictionary<string, object>
                        {
                            ["archive"] = archiveFullPath,
                            ["section_file_offset"] = section.Descriptor.FileOffset,
                            ["stored_size"] = section.Descriptor.ReadSize,
                            ["decoded_size"] = section.Descriptor.DataSize,
                            ["compressed"] = section.Descriptor.IsCompressed,
                            ["payload_start"] = chunk.PayloadStart,
                            ["payload_size"] = chunk.PayloadSize,
                            ["resource_type"] = chunk.ResourceType
                        };

                        long memberId;
                        using (var mCmd = db.CreateCommand())
                        {
                            mCmd.CommandText = @"
INSERT INTO files(view, root, path, level, format, size, sha256, archive, member, locator, status, language)
VALUES('member', @root, @path, @level, @format, @size, @sha256, @archive, @member, @locator, 'original archive member', 'ANY');
SELECT last_insert_rowid();";
                            mCmd.Parameters.AddWithValue("@root", _sourceRoot);
                            mCmd.Parameters.AddWithValue("@path", relPath);
                            mCmd.Parameters.AddWithValue("@level", level);
                            mCmd.Parameters.AddWithValue("@format", format);
                            mCmd.Parameters.AddWithValue("@size", chunk.PayloadSize);
                            mCmd.Parameters.AddWithValue("@sha256", sha);
                            mCmd.Parameters.AddWithValue("@archive", archiveId);
                            mCmd.Parameters.AddWithValue("@member", memberName);
                            mCmd.Parameters.AddWithValue("@locator", JsonSerializer.Serialize(locator));
                            memberId = Convert.ToInt64(mCmd.ExecuteScalar());
                        }

                        if (!shaMap.TryGetValue(sha, out var list))
                        {
                            list = new List<long>();
                            shaMap[sha] = list;
                        }
                        list.Add(memberId);

                        // Insert asset GUID
                        if (!string.IsNullOrEmpty(chunk.AssetGuid))
                        {
                            InsertId(db, memberId, "asset.guid", chunk.AssetGuid, "definition", 0, 16, "BE words", "STR asset metadata GUID", "provenance", "origin STR metadata");
                        }

                        // Extract payload identifiers
                        var (extractedIds, _) = IdentifierExtractor.Extract(chunk.PayloadData, format);
                        foreach (var id in extractedIds)
                        {
                            InsertId(db, memberId, id.Namespace, id.Value, id.Role, id.Offset, id.Width, id.Endian, id.Label, id.Confidence, id.Region);
                        }
                    }
                }
            }
        }
        catch
        {
            // Skip invalid archives
        }
    }

    private void IndexStandaloneFile(SqliteConnection db, string root, string relPath, string fullPath, string level, string status, Dictionary<string, List<long>> shaMap)
    {
        long size = new FileInfo(fullPath).Length;
        string format = FormatDetector.Identify(relPath);
        string sha = ComputeSha256(fullPath);

        long fileId;
        using (var ins = db.CreateCommand())
        {
            ins.CommandText = @"
INSERT INTO files(view, root, path, level, format, size, sha256, archive, member, locator, status, language)
VALUES('source', @root, @path, @level, @format, @size, @sha256, NULL, NULL, '{}', @status, 'ANY');
SELECT last_insert_rowid();";
            ins.Parameters.AddWithValue("@root", root);
            ins.Parameters.AddWithValue("@path", relPath);
            ins.Parameters.AddWithValue("@level", level);
            ins.Parameters.AddWithValue("@format", format);
            ins.Parameters.AddWithValue("@size", size);
            ins.Parameters.AddWithValue("@sha256", sha);
            ins.Parameters.AddWithValue("@status", status);
            fileId = Convert.ToInt64(ins.ExecuteScalar());
        }

        if (!shaMap.TryGetValue(sha, out var list))
        {
            list = new List<long>();
            shaMap[sha] = list;
        }
        list.Add(fileId);

        if (size <= _maxParseBytes)
        {
            byte[] data = File.ReadAllBytes(fullPath);
            var (extractedIds, _) = IdentifierExtractor.Extract(data, format);
            foreach (var id in extractedIds)
            {
                InsertId(db, fileId, id.Namespace, id.Value, id.Role, id.Offset, id.Width, id.Endian, id.Label, id.Confidence, id.Region);
            }
        }
    }

    private static void InsertId(SqliteConnection db, long fileId, string ns, string val, string role, int offset, int width, string endian, string label, string confidence, string region)
    {
        using var cmd = db.CreateCommand();
        cmd.CommandText = "INSERT INTO ids(file, namespace, value, role, offset, width, endian, label, confidence, doc, region) VALUES(@file, @ns, @val, @role, @offset, @width, @endian, @label, @conf, '', @region)";
        cmd.Parameters.AddWithValue("@file", fileId);
        cmd.Parameters.AddWithValue("@ns", ns);
        cmd.Parameters.AddWithValue("@val", val);
        cmd.Parameters.AddWithValue("@role", role);
        cmd.Parameters.AddWithValue("@offset", offset);
        cmd.Parameters.AddWithValue("@width", width);
        cmd.Parameters.AddWithValue("@endian", endian);
        cmd.Parameters.AddWithValue("@label", label);
        cmd.Parameters.AddWithValue("@conf", confidence);
        cmd.Parameters.AddWithValue("@region", region);
        cmd.ExecuteNonQuery();
    }

    private static string InferLevel(string path)
    {
        string lower = path.Replace('\\', '/').ToLowerInvariant();
        string[] parts = lower.Split('/');
        if (parts.Length > 0)
        {
            string top = parts[0];
            if (top.StartsWith("a1_") || top.StartsWith("a2_") || top.StartsWith("a3_") || top.StartsWith("a4_") ||
                top.StartsWith("h1_") || top.StartsWith("m1_") || top.StartsWith("b1_"))
            {
                return parts[0];
            }
        }
        return "Shared";
    }

    private static string ComputeSha256(string filePath)
    {
        using var sha = SHA256.Create();
        using var fs = File.OpenRead(filePath);
        byte[] hash = sha.ComputeHash(fs);
        return Convert.ToHexString(hash).ToLowerInvariant();
    }

    private static string ComputeSha256(byte[] data)
    {
        using var sha = SHA256.Create();
        byte[] hash = sha.ComputeHash(data);
        return Convert.ToHexString(hash).ToLowerInvariant();
    }
}

