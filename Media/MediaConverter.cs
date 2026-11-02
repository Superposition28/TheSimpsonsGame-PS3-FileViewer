using System.Buffers.Binary;
using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace TheSimpsonsGame.FileViewer.Media;

public class MediaConverter
{
    private static MediaConverter? _instance;
    public static MediaConverter Instance => _instance ??= new MediaConverter();

    private readonly string _tempRoot;

    public MediaConverter()
    {
        _tempRoot = Path.Combine(Path.GetTempPath(), "TheSimpsonsGame-FileViewer");
        Directory.CreateDirectory(_tempRoot);
    }

    public static string? FindTool(string name, string moduleRoot)
    {
        string toolsDir = Path.GetFullPath(Path.Combine(moduleRoot, "..", "..", "Tools"));
        if (!Directory.Exists(toolsDir))
        {
            toolsDir = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", "..", "Tools"));
        }

        if (Directory.Exists(toolsDir))
        {
            if (name.Equals("ffmpeg", StringComparison.OrdinalIgnoreCase))
            {
                var match = Directory.GetFiles(toolsDir, "ffmpeg.exe", SearchOption.AllDirectories).FirstOrDefault();
                if (match != null) return match;
            }
            else if (name.Equals("vgmstream", StringComparison.OrdinalIgnoreCase) ||
                     name.Equals("vgmstream-cli", StringComparison.OrdinalIgnoreCase))
            {
                var match = Directory.GetFiles(toolsDir, "vgmstream-cli.exe", SearchOption.AllDirectories).FirstOrDefault();
                if (match != null) return match;
            }
            else if (name.Equals("blender", StringComparison.OrdinalIgnoreCase))
            {
                var match = Directory.GetFiles(toolsDir, "blender.exe", SearchOption.AllDirectories).FirstOrDefault();
                if (match != null) return match;
            }
        }

        return null;
    }

    public async Task<List<string>> ConvertAsync(string sourcePath, byte[]? data, string fileName, string moduleRoot)
    {
        string ext = Path.GetExtension(string.IsNullOrEmpty(fileName) ? sourcePath : fileName).ToLowerInvariant();

        // 1. Directly playable media
        if (ext is ".wav" or ".ogg" or ".mp3" or ".flac" or ".ogv" or ".mp4" or ".avi" or ".webm" or ".png" or ".jpg" or ".jpeg" or ".bmp")
        {
            if (File.Exists(sourcePath))
                return new List<string> { sourcePath };
        }

        // 2. Cache key calculation
        string key = ComputeKey(sourcePath, data, fileName);
        string outputDir = Path.Combine(_tempRoot, key);
        Directory.CreateDirectory(outputDir);

        string manifestPath = Path.Combine(outputDir, "outputs.json");
        if (File.Exists(manifestPath))
        {
            try
            {
                var cached = JsonSerializer.Deserialize<List<string>>(File.ReadAllText(manifestPath));
                if (cached != null && cached.Count > 0 && cached.All(File.Exists))
                {
                    return cached;
                }
            }
            catch { }
        }

        // Prepare input file in temp directory if not on disk
        string inputPath = sourcePath;
        if (!File.Exists(inputPath))
        {
            inputPath = Path.Combine(outputDir, $"input{ext}");
            if (data != null)
            {
                await File.WriteAllBytesAsync(inputPath, data);
            }
            else
            {
                throw new FileNotFoundException($"Source data not found for {fileName}");
            }
        }

        var results = new List<string>();

        // 3. Format conversion
        if (ext == ".vp6")
        {
            string? ffmpeg = FindTool("ffmpeg", moduleRoot);
            if (ffmpeg == null) throw new FileNotFoundException("ffmpeg.exe not found in Tools directory");

            string outputOgv = Path.Combine(outputDir, "preview.ogv");
            string args = $"-y -loglevel error -i \"{inputPath}\" -c:v libtheora -q:v 10 -c:a libvorbis -q:a 10 \"{outputOgv}\"";

            await RunProcessAsync(ffmpeg, args, outputDir);
            if (File.Exists(outputOgv))
            {
                results.Add(outputOgv);
            }
            else
            {
                // Fallback to mp4
                string outputMp4 = Path.Combine(outputDir, "preview.mp4");
                string mp4Args = $"-y -loglevel error -i \"{inputPath}\" -c:v libx264 -preset fast -crf 20 -c:a aac \"{outputMp4}\"";
                await RunProcessAsync(ffmpeg, mp4Args, outputDir);
                if (File.Exists(outputMp4)) results.Add(outputMp4);
            }
        }
        else if (ext is ".snu" or ".snr")
        {
            string? vgm = FindTool("vgmstream", moduleRoot);
            if (vgm == null) throw new FileNotFoundException("vgmstream-cli.exe not found in Tools directory");

            string rawWav = Path.Combine(outputDir, "raw.wav");
            await RunProcessAsync(vgm, $"-i -o \"{rawWav}\" \"{inputPath}\"", outputDir);

            if (File.Exists(rawWav))
            {
                int channels = GetWavChannels(rawWav);
                string? ffmpeg = FindTool("ffmpeg", moduleRoot);

                if (channels == 4 && ffmpeg != null)
                {
                    string frontWav = Path.Combine(outputDir, "preview_front.wav");
                    string rearWav = Path.Combine(outputDir, "preview_rear.wav");
                    string quadFilter = "\"[0:a]channelsplit=channel_layout=quad[FL][FR][BL][BR];[FL][FR]join=inputs=2:channel_layout=stereo[FRONT];[BL][BR]join=inputs=2:channel_layout=stereo[REAR]\"";
                    string splitArgs = $"-y -loglevel error -i \"{rawWav}\" -filter_complex {quadFilter} -map \"[FRONT]\" -c:a pcm_s16le \"{frontWav}\" -map \"[REAR]\" -c:a pcm_s16le \"{rearWav}\"";

                    await RunProcessAsync(ffmpeg, splitArgs, outputDir);
                    if (File.Exists(frontWav) && File.Exists(rearWav))
                    {
                        try { File.Delete(rawWav); } catch { }
                        results.Add(frontWav);
                        results.Add(rearWav);
                    }
                    else
                    {
                        results.Add(rawWav);
                    }
                }
                else
                {
                    string previewWav = Path.Combine(outputDir, "preview.wav");
                    if (File.Exists(previewWav)) File.Delete(previewWav);
                    File.Move(rawWav, previewWav);
                    results.Add(previewWav);
                }
            }
        }
        else if (ext == ".sbk")
        {
            string? vgm = FindTool("vgmstream", moduleRoot);
            if (vgm == null) throw new FileNotFoundException("vgmstream-cli.exe not found in Tools directory");

            string bankDir = Path.Combine(outputDir, "decoded-bank");
            Directory.CreateDirectory(bankDir);
            string pattern = Path.Combine(bankDir, "track_?s.wav");

            await RunProcessAsync(vgm, $"-i -S 0 -o \"{pattern}\" \"{inputPath}\"", outputDir);

            var tracks = Directory.GetFiles(bankDir, "track_*.wav").OrderBy(f => f).ToList();
            if (tracks.Count > 0)
            {
                results.AddRange(tracks);
            }
            else
            {
                throw new InvalidOperationException("vgmstream produced no bank tracks for SBK");
            }
        }
        else if (ext == ".mus")
        {
            byte[] musBytes = data ?? (File.Exists(sourcePath) ? await File.ReadAllBytesAsync(sourcePath) : Array.Empty<byte>());
            var segments = ExtractMusSegments(musBytes);

            string? vgm = FindTool("vgmstream", moduleRoot);
            if (vgm == null) throw new FileNotFoundException("vgmstream-cli.exe not found in Tools directory");

            for (int i = 0; i < segments.Count; i++)
            {
                var seg = segments[i];
                string stem = $"segment_{seg.Index:D3}";
                string snrPath = Path.Combine(outputDir, $"{stem}.snr");
                string snsPath = Path.Combine(outputDir, $"{stem}.sns");
                string wavPath = Path.Combine(outputDir, $"{stem}.wav");

                await File.WriteAllBytesAsync(snrPath, seg.Snr);
                await File.WriteAllBytesAsync(snsPath, seg.Sns);

                await RunProcessAsync(vgm, $"-i -o \"{wavPath}\" \"{snrPath}\"", outputDir);
                if (File.Exists(wavPath))
                {
                    results.Add(wavPath);
                }
            }

            if (results.Count == 0)
            {
                throw new InvalidOperationException("Failed to decode any MUS music segments");
            }
        }
        else
        {
            results.Add(inputPath);
        }

        if (results.Count > 0)
        {
            try
            {
                await File.WriteAllTextAsync(manifestPath, JsonSerializer.Serialize(results));
            }
            catch { }
        }

        return results;
    }

    public static List<(int Index, byte[] Snr, byte[] Sns)> ExtractMusSegments(byte[] data)
    {
        var segments = new List<(int Index, byte[] Snr, byte[] Sns)>();
        if (data.Length < 40) return segments;

        int count = data[4];
        for (int i = 0; i < count; i++)
        {
            int pos = 40 + i * 28;
            if (pos + 28 > data.Length) break;

            uint snrUnit = BinaryPrimitives.ReadUInt32BigEndian(data.AsSpan(pos + 8, 4));
            uint snsUnit = BinaryPrimitives.ReadUInt32BigEndian(data.AsSpan(pos + 12, 4));
            uint snrSize = BinaryPrimitives.ReadUInt32BigEndian(data.AsSpan(pos + 16, 4));
            uint snsSize = BinaryPrimitives.ReadUInt32BigEndian(data.AsSpan(pos + 20, 4));

            int snrOffset = (int)(snrUnit * 16);
            int snsOffset = (int)(snsUnit * 128);

            if (snrOffset + (int)snrSize <= data.Length && snsOffset + (int)snsSize <= data.Length)
            {
                byte[] snrData = data.AsSpan(snrOffset, (int)snrSize).ToArray();
                byte[] snsData = data.AsSpan(snsOffset, (int)snsSize).ToArray();
                segments.Add((i, snrData, snsData));
            }
        }
        return segments;
    }

    public static int GetWavChannels(string wavPath)
    {
        try
        {
            using var fs = new FileStream(wavPath, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
            using var br = new BinaryReader(fs);
            if (fs.Length < 12) return 2;

            byte[] riff = br.ReadBytes(4);
            uint fileSize = br.ReadUInt32();
            byte[] wave = br.ReadBytes(4);

            while (fs.Position + 8 <= fs.Length)
            {
                byte[] chunkId = br.ReadBytes(4);
                uint chunkSize = br.ReadUInt32();
                string id = Encoding.ASCII.GetString(chunkId);
                if (id == "fmt " && chunkSize >= 4)
                {
                    ushort formatTag = br.ReadUInt16();
                    ushort channels = br.ReadUInt16();
                    return channels;
                }
                fs.Seek(chunkSize + (chunkSize & 1), SeekOrigin.Current);
            }
        }
        catch { }
        return 2;
    }

    private static async Task RunProcessAsync(string toolExe, string args, string workingDir)
    {
        using var proc = new Process
        {
            StartInfo = new ProcessStartInfo
            {
                FileName = toolExe,
                Arguments = args,
                WorkingDirectory = workingDir,
                CreateNoWindow = true,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true
            }
        };

        proc.Start();
        string output = await proc.StandardOutput.ReadToEndAsync();
        string error = await proc.StandardError.ReadToEndAsync();
        await proc.WaitForExitAsync();

        if (proc.ExitCode != 0 && !string.IsNullOrEmpty(error))
        {
            // Log if needed
            string logFile = Path.Combine(workingDir, "conversion.log");
            try { await File.AppendAllTextAsync(logFile, $"[{DateTime.UtcNow}] {toolExe} {args}\nError: {error}\nOutput: {output}\n"); } catch { }
        }
    }

    private static string ComputeKey(string sourcePath, byte[]? data, string fileName)
    {
        string identity;
        if (!string.IsNullOrEmpty(sourcePath) && File.Exists(sourcePath))
        {
            var fi = new FileInfo(sourcePath);
            identity = $"{fi.FullName}:{fi.Length}:{fi.LastWriteTimeUtc.Ticks}";
        }
        else
        {
            identity = $"{fileName}:{data?.Length ?? 0}:{Convert.ToHexString(SHA256.HashData(data ?? Array.Empty<byte>()))}";
        }
        return Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(identity))).ToLowerInvariant();
    }

    public void OpenDefault(string filePath)
    {
        if (File.Exists(filePath))
        {
            try
            {
                Process.Start(new ProcessStartInfo
                {
                    FileName = filePath,
                    UseShellExecute = true
                });
            }
            catch { }
        }
    }
}
