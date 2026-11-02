using System.Diagnostics;

namespace TheSimpsonsGame.FileViewer.Media;

public static class MediaManager
{
    private static readonly HashSet<string> AudioExts = new(StringComparer.OrdinalIgnoreCase)
    {
        ".snu", ".exa.snu", ".sbk", ".mus", ".wav", ".ogg", ".mp3", ".flac", ".snr"
    };

    private static readonly HashSet<string> VideoExts = new(StringComparer.OrdinalIgnoreCase)
    {
        ".vp6", ".ogv", ".mp4", ".avi", ".webm"
    };

    private static readonly HashSet<string> ImageExts = new(StringComparer.OrdinalIgnoreCase)
    {
        ".png", ".dds", ".jpg", ".jpeg", ".bmp", ".tga"
    };

    public static bool IsMedia(string path)
    {
        string ext = Path.GetExtension(path).ToLowerInvariant();
        return AudioExts.Contains(ext) || VideoExts.Contains(ext) || ImageExts.Contains(ext) || path.EndsWith(".exa.snu", StringComparison.OrdinalIgnoreCase);
    }

    public static string GetButtonLabel(string path)
    {
        string ext = Path.GetExtension(path).ToLowerInvariant();
        if (VideoExts.Contains(ext)) return "Watch";
        if (ImageExts.Contains(ext)) return "Open image";
        return "Play";
    }

    public static string GetTempDirectory()
    {
        string temp = Path.Combine(Path.GetTempPath(), "TheSimpsonsGame-FileViewer");
        Directory.CreateDirectory(temp);
        return temp;
    }

    public static void PlayOrOpen(string fileName, byte[] data)
    {
        string tempDir = GetTempDirectory();
        string safeName = Path.GetFileName(fileName);
        if (string.IsNullOrWhiteSpace(safeName)) safeName = "media_preview.bin";
        string outPath = Path.Combine(tempDir, safeName);

        File.WriteAllBytes(outPath, data);

        try
        {
            Process.Start(new ProcessStartInfo
            {
                FileName = outPath,
                UseShellExecute = true
            });
        }
        catch (Exception ex)
        {
            throw new InvalidOperationException($"Failed to open media: {ex.Message}", ex);
        }
    }
}

