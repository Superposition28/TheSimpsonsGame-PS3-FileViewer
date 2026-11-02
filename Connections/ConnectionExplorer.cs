using System.Buffers.Binary;
using System.Collections.Concurrent;
using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.Data.Sqlite;
using TheSimpsonsGame.FileViewer.Formats;
using TheSimpsonsGame.FileViewer.IO;

namespace TheSimpsonsGame.FileViewer.Connections;

public class ConnectionExplorer : IDisposable
{
    private readonly string _databasePath;
    private readonly SqliteConnection _db;
    private readonly ConcurrentDictionary<string, byte[]> _sectionCache = new();

    public ConnectionExplorer(string databasePath)
    {
        _databasePath = databasePath;
        var builder = new SqliteConnectionStringBuilder
        {
            DataSource = databasePath,
            Mode = SqliteOpenMode.ReadOnly
        };
        _db = new SqliteConnection(builder.ConnectionString);
        _db.Open();
    }

    public void Dispose()
    {
        _db.Dispose();
    }

    public Dictionary<string, object> GetSummary()
    {
        var result = new Dictionary<string, object>();
        using var cmd = _db.CreateCommand();
        cmd.CommandText = "SELECT value FROM meta WHERE key='summary'";
        var val = cmd.ExecuteScalar()?.ToString();
        if (!string.IsNullOrEmpty(val))
        {
            var parsed = JsonSerializer.Deserialize<Dictionary<string, object>>(val);
            if (parsed != null) result = parsed;
        }

        // Add levels
        var levels = new List<Dictionary<string, object>>();
        using var lvlCmd = _db.CreateCommand();
        lvlCmd.CommandText = "SELECT level, COUNT(*) AS count FROM files GROUP BY level ORDER BY level";
        using var lvlRdr = lvlCmd.ExecuteReader();
        while (lvlRdr.Read())
        {
            levels.Add(new Dictionary<string, object>
            {
                ["level"] = lvlRdr.GetString(0),
                ["count"] = lvlRdr.GetInt64(1)
            });
        }
        result["levels"] = levels;

        // Add formats
        var formats = new List<Dictionary<string, object>>();
        using var fmtCmd = _db.CreateCommand();
        fmtCmd.CommandText = "SELECT format, COUNT(*) AS count FROM files GROUP BY format ORDER BY format";
        using var fmtRdr = fmtCmd.ExecuteReader();
        while (fmtRdr.Read())
        {
            formats.Add(new Dictionary<string, object>
            {
                ["format"] = fmtRdr.GetString(0),
                ["count"] = fmtRdr.GetInt64(1)
            });
        }
        result["formats"] = formats;

        // Add statuses
        var statuses = new List<Dictionary<string, object>>();
        using var stCmd = _db.CreateCommand();
        stCmd.CommandText = "SELECT status, COUNT(*) AS count FROM files GROUP BY status ORDER BY COUNT(*) DESC LIMIT 50";
        using var stRdr = stCmd.ExecuteReader();
        while (stRdr.Read())
        {
            statuses.Add(new Dictionary<string, object>
            {
                ["status"] = stRdr.GetString(0),
                ["count"] = stRdr.GetInt64(1)
            });
        }
        result["statuses"] = statuses;

        return result;
    }

    public Dictionary<string, object> SearchFiles(string level, string q, string view, string format, int offset, int limit, bool shared)
    {
        var conditions = new List<string>();
        var parameters = new List<SqliteParameter>();

        if (!string.IsNullOrEmpty(level))
        {
            if (shared)
            {
                conditions.Add("(level = @level OR level = 'Shared')");
            }
            else
            {
                conditions.Add("level = @level");
            }
            parameters.Add(new SqliteParameter("@level", level));
        }

        if (!string.IsNullOrEmpty(view) && view != "both")
        {
            conditions.Add("view = @view");
            parameters.Add(new SqliteParameter("@view", view));
        }

        if (!string.IsNullOrEmpty(format))
        {
            conditions.Add("format = @format");
            parameters.Add(new SqliteParameter("@format", format));
        }

        if (!string.IsNullOrEmpty(q))
        {
            conditions.Add("(path LIKE @q OR member LIKE @q)");
            parameters.Add(new SqliteParameter("@q", $"%{q}%"));
        }

        string where = conditions.Count > 0 ? "WHERE " + string.Join(" AND ", conditions) : "";

        long total = 0;
        using (var countCmd = _db.CreateCommand())
        {
            countCmd.CommandText = $"SELECT COUNT(*) FROM files {where}";
            foreach (var p in parameters) countCmd.Parameters.Add(new SqliteParameter(p.ParameterName, p.Value));
            total = Convert.ToInt64(countCmd.ExecuteScalar());
        }

        var files = new List<Dictionary<string, object>>();
        using (var cmd = _db.CreateCommand())
        {
            cmd.CommandText = $"SELECT * FROM files {where} ORDER BY level, path LIMIT @limit OFFSET @offset";
            foreach (var p in parameters) cmd.Parameters.Add(new SqliteParameter(p.ParameterName, p.Value));
            cmd.Parameters.Add(new SqliteParameter("@limit", limit));
            cmd.Parameters.Add(new SqliteParameter("@offset", offset));

            using var rdr = cmd.ExecuteReader();
            while (rdr.Read())
            {
                files.Add(ReadRow(rdr));
            }
        }

        return new Dictionary<string, object>
        {
            ["files"] = files,
            ["total"] = total,
            ["limit"] = limit,
            ["offset"] = offset
        };
    }

    public Dictionary<string, object>? GetFile(long id)
    {
        using var cmd = _db.CreateCommand();
        cmd.CommandText = "SELECT * FROM files WHERE id = @id";
        cmd.Parameters.AddWithValue("@id", id);
        using var rdr = cmd.ExecuteReader();
        if (rdr.Read())
        {
            return ReadRow(rdr);
        }
        return null;
    }

    public byte[] ReadFileBytes(Dictionary<string, object> file, int start = 0, int? length = null)
    {
        string view = file.TryGetValue("view", out var v) ? v?.ToString() ?? "" : "";
        if (view != "member")
        {
            string root = file["root"]?.ToString() ?? "";
            string path = file["path"]?.ToString() ?? "";
            string fullPath = Path.Combine(root, path);
            if (!File.Exists(fullPath)) return Array.Empty<byte>();

            using var fs = File.OpenRead(fullPath);
            fs.Seek(start, SeekOrigin.Begin);
            int readLen = length ?? (int)(fs.Length - start);
            byte[] buffer = new byte[readLen];
            int read = fs.Read(buffer, 0, readLen);
            if (read < readLen) Array.Resize(ref buffer, read);
            return buffer;
        }

        string locatorJson = file["locator"]?.ToString() ?? "{}";
        using var doc = JsonDocument.Parse(locatorJson);
        var rootElem = doc.RootElement;

        string archive = rootElem.GetProperty("archive").GetString() ?? "";
        long sectionFileOffset = rootElem.GetProperty("section_file_offset").GetInt64();
        int storedSize = rootElem.GetProperty("stored_size").GetInt32();
        int decodedSize = rootElem.GetProperty("decoded_size").GetInt32();
        bool compressed = rootElem.GetProperty("compressed").GetBoolean();
        int payloadStart = rootElem.GetProperty("payload_start").GetInt32();
        int payloadSize = rootElem.GetProperty("payload_size").GetInt32();

        string cacheKey = $"{archive}_{sectionFileOffset}_{storedSize}";
        if (!_sectionCache.TryGetValue(cacheKey, out var sectionBytes))
        {
            if (!File.Exists(archive)) return Array.Empty<byte>();
            using var fs = File.OpenRead(archive);
            fs.Seek(sectionFileOffset, SeekOrigin.Begin);
            byte[] packed = new byte[storedSize];
            fs.Read(packed, 0, storedSize);

            sectionBytes = compressed ? RefPack.Decompress(packed, decodedSize) : packed.AsSpan(0, Math.Min(decodedSize, storedSize)).ToArray();
            _sectionCache[cacheKey] = sectionBytes;
        }

        int offset = payloadStart + start;
        int count = length ?? (payloadSize - start);
        if (offset < 0 || offset >= sectionBytes.Length) return Array.Empty<byte>();
        int available = Math.Min(count, sectionBytes.Length - offset);
        byte[] result = new byte[available];
        Array.Copy(sectionBytes, offset, result, 0, available);
        return result;
    }

    public Dictionary<string, object> GetFileIdentifiers(long id, int offset, int limit, string view, bool cross, string language)
    {
        var file = GetFile(id);
        if (file == null) throw new InvalidOperationException("File not found");

        long total = 0;
        using (var countCmd = _db.CreateCommand())
        {
            countCmd.CommandText = "SELECT COUNT(*) FROM ids WHERE file = @file";
            countCmd.Parameters.AddWithValue("@file", id);
            total = Convert.ToInt64(countCmd.ExecuteScalar());
        }

        var ids = new List<Dictionary<string, object>>();
        using (var cmd = _db.CreateCommand())
        {
            cmd.CommandText = "SELECT * FROM ids WHERE file = @file ORDER BY offset LIMIT @limit OFFSET @offset";
            cmd.Parameters.AddWithValue("@file", id);
            cmd.Parameters.AddWithValue("@limit", limit);
            cmd.Parameters.AddWithValue("@offset", offset);

            using var rdr = cmd.ExecuteReader();
            while (rdr.Read())
            {
                var row = ReadRow(rdr);
                row["resolution"] = ResolveObservation(row, file, view, cross, language);
                ids.Add(row);
            }
        }

        var provenance = new List<Dictionary<string, object>>();
        using (var edgeCmd = _db.CreateCommand())
        {
            edgeCmd.CommandText = "SELECT * FROM edges WHERE source = @id OR target = @id LIMIT 200";
            edgeCmd.Parameters.AddWithValue("@id", id);
            using var rdr = edgeCmd.ExecuteReader();
            while (rdr.Read()) provenance.Add(ReadRow(rdr));
        }

        return new Dictionary<string, object>
        {
            ["file"] = file,
            ["identifiers"] = ids,
            ["total"] = total,
            ["limit"] = limit,
            ["offset"] = offset,
            ["provenance"] = provenance
        };
    }

    public Dictionary<string, object> ResolveObservation(Dictionary<string, object> observation, Dictionary<string, object> source, string view, bool cross, string language, int limit = 8)
    {
        string ns = observation["namespace"]?.ToString() ?? "";
        string val = observation["value"]?.ToString() ?? "";

        var spaces = ns == "bone.binding" ? new[] { "bone.alias", "bone.rig" } : new[] { ns };
        string inClause = string.Join(",", spaces.Select((_, idx) => $"@ns{idx}"));

        using var cmd = _db.CreateCommand();
        cmd.CommandText = $@"
SELECT f.*, i.id AS definition, i.offset AS target_offset, i.region AS target_region, i.label AS target_label, i.namespace AS target_namespace
FROM ids i
JOIN files f ON f.id = i.file
WHERE i.role = 'definition' AND i.namespace IN ({inClause}) AND i.value = @val
LIMIT 500";

        for (int i = 0; i < spaces.Length; i++) cmd.Parameters.AddWithValue($"@ns{i}", spaces[i]);
        cmd.Parameters.AddWithValue("@val", val);

        var rows = new List<Dictionary<string, object>>();
        using var rdr = cmd.ExecuteReader();
        while (rdr.Read()) rows.Add(ReadRow(rdr));

        string sourceLevel = source["level"]?.ToString() ?? "";
        string sourceLang = source["language"]?.ToString() ?? "ANY";
        string wantedLang = language == "auto" ? sourceLang : language;
        int excluded = 0;

        var ranked = new List<(int Rank, Dictionary<string, object> Target)>();

        foreach (var r in rows)
        {
            string targetLevel = r["level"]?.ToString() ?? "";
            if (targetLevel != sourceLevel && targetLevel != "Shared" && !cross)
            {
                excluded++;
                continue;
            }

            string targetLang = r["language"]?.ToString() ?? "ANY";
            if (wantedLang != "ANY" && wantedLang != "MULTI" && targetLang != wantedLang && targetLang != "MULTI" && targetLang != "ANY")
            {
                continue;
            }

            int rank = (targetLevel == sourceLevel) ? 0 : (targetLevel == "Shared" ? 1 : 2);
            ranked.Add((rank, r));
        }

        ranked.Sort((a, b) => a.Rank.CompareTo(b.Rank));

        var targets = ranked.Take(limit).Select(x => x.Target).ToList();
        var alternatives = ranked.Skip(limit).Take(20).Select(x => x.Target).ToList();

        string status = targets.Count == 0 ? "unresolved" : (targets.Count == 1 ? "resolved" : "ambiguous");

        return new Dictionary<string, object>
        {
            ["status"] = status,
            ["targets"] = targets,
            ["alternatives"] = alternatives,
            ["candidate_files"] = ranked.Count,
            ["excluded_cross_level"] = excluded
        };
    }

    public Dictionary<string, object> GetGraph(long id, int depth, int maximum, bool incoming, string view, bool cross, string language)
    {
        var file = GetFile(id);
        if (file == null) throw new InvalidOperationException("File not found");

        var fileMap = new Dictionary<long, Dictionary<string, object>> { [id] = file };
        var idList = new List<Dictionary<string, object>>();
        var edges = new List<Dictionary<string, object>>();

        // Read identifiers of focus file
        using (var cmd = _db.CreateCommand())
        {
            cmd.CommandText = "SELECT * FROM ids WHERE file = @file LIMIT @limit";
            cmd.Parameters.AddWithValue("@file", id);
            cmd.Parameters.AddWithValue("@limit", maximum);

            using var rdr = cmd.ExecuteReader();
            while (rdr.Read())
            {
                var row = ReadRow(rdr);
                var res = ResolveObservation(row, file, view, cross, language, limit: 4);
                row["resolution"] = res;
                idList.Add(row);

                string obsKey = "i" + row["id"];
                edges.Add(new Dictionary<string, object>
                {
                    ["source"] = "f" + id,
                    ["target"] = obsKey,
                    ["kind"] = row["confidence"]?.ToString() ?? "structural",
                    ["label"] = row["namespace"]?.ToString() ?? ""
                });

                if (res.TryGetValue("targets", out var tObj) && tObj is List<Dictionary<string, object>> targetList)
                {
                    foreach (var target in targetList)
                    {
                        long tId = Convert.ToInt64(target["id"]);
                        if (!fileMap.ContainsKey(tId))
                        {
                            fileMap[tId] = target;
                        }
                        edges.Add(new Dictionary<string, object>
                        {
                            ["source"] = obsKey,
                            ["target"] = "f" + tId,
                            ["kind"] = res["status"]?.ToString() ?? "structural",
                            ["label"] = res["status"]?.ToString() ?? ""
                        });
                    }
                }
            }
        }

        return new Dictionary<string, object>
        {
            ["files"] = fileMap.Values.ToList(),
            ["identifiers"] = idList,
            ["edges"] = edges,
            ["focus"] = id,
            ["truncated"] = idList.Count >= maximum,
            ["maximum"] = maximum,
            ["notice"] = $"{fileMap.Count} files and {idList.Count} identifiers in graph"
        };
    }

    public Dictionary<string, object> GetWords(long id, int offset, int limit, int stride)
    {
        var file = GetFile(id);
        if (file == null) throw new InvalidOperationException("File not found");

        long size = Convert.ToInt64(file["size"]);
        byte[] data = ReadFileBytes(file, offset, limit * stride);

        var words = new List<Dictionary<string, object>>();
        for (int i = 0; i + 4 <= data.Length; i += stride)
        {
            int currentOffset = offset + i;
            uint be = BinaryPrimitives.ReadUInt32BigEndian(data.AsSpan(i, 4));
            uint le = BinaryPrimitives.ReadUInt32LittleEndian(data.AsSpan(i, 4));
            string rawHex = Convert.ToHexString(data.AsSpan(i, 4));

            words.Add(new Dictionary<string, object>
            {
                ["offset"] = currentOffset,
                ["raw"] = rawHex,
                ["be"] = be,
                ["le"] = le,
                ["matches"] = new List<object>()
            });
        }

        return new Dictionary<string, object>
        {
            ["words"] = words,
            ["size"] = size,
            ["next_offset"] = offset + data.Length,
            ["step"] = stride
        };
    }

    public Dictionary<string, object> GetCopies(long id)
    {
        var file = GetFile(id);
        if (file == null) throw new InvalidOperationException("File not found");

        string sha = file["sha256"]?.ToString() ?? "";
        var copies = new List<Dictionary<string, object>>();

        if (!string.IsNullOrEmpty(sha))
        {
            using var cmd = _db.CreateCommand();
            cmd.CommandText = "SELECT * FROM files WHERE sha256 = @sha AND sha256 != '' ORDER BY level, path LIMIT 200";
            cmd.Parameters.AddWithValue("@sha", sha);
            using var rdr = cmd.ExecuteReader();
            while (rdr.Read()) copies.Add(ReadRow(rdr));
        }

        return new Dictionary<string, object> { ["copies"] = copies };
    }

    private static Dictionary<string, object> ReadRow(SqliteDataReader rdr)
    {
        var dict = new Dictionary<string, object>();
        for (int i = 0; i < rdr.FieldCount; i++)
        {
            dict[rdr.GetName(i)] = rdr.IsDBNull(i) ? "" : rdr.GetValue(i);
        }
        return dict;
    }
}
