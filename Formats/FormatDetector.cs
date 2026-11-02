using System.Text;

namespace TheSimpsonsGame.FileViewer.Formats;

public static class FormatDetector
{
    public static readonly HashSet<string> PartialFormats = new(StringComparer.OrdinalIgnoreCase)
    {
        ".amb", ".aub", ".bnk.ps3", ".ctb", ".mib", ".msb", ".rcb.ps3", ".rcm_b",
        ".sbk", ".toc", ".uix", ".xml.ps3", ".ps3", ".itxd", ".bin", ".elf", ".snu", ".vp6"
    };

    public static readonly HashSet<string> LegacyFormats = new(StringComparer.OrdinalIgnoreCase)
    {
        ".graph", ".meta.xml", ".cec.ps3", ".shk.ps3", ".preinstanced", ".txd", ".rws", ".dff", ".tob"
    };

    private static readonly Dictionary<string, string> ResourceKinds = new(StringComparer.OrdinalIgnoreCase)
    {
        ["UIE"] = ".dat.uie",
        ["CEC"] = ".cec.ps3",
        ["SHK"] = ".shk.ps3",
        ["TOB"] = ".tox.ps3",
        ["TOX"] = ".tox.ps3",
        ["METAMODEL"] = ".meta.xml",
        ["GRAPH"] = ".graph",
        ["EARS_MESH"] = ".preinstanced",
        ["LIGHTTOC"] = "lighttoc",
        ["STREAMSETCONFIG"] = "streamsetconfig"
    };

    private static readonly string[] SuffixesDescending = new[]
    {
        ".streamsetconfig", ".dat.simgroup", ".simgroup.dat", ".dat.uie", ".tox.ps3",
        ".bbn.ps3", ".acs.ps3", ".cec.ps3", ".rcb.ps3", ".xml.ps3", ".meta.xml",
        ".preinstanced", ".bnk.ps3", ".hkt.ps3", ".shk.ps3", ".lighttoc", ".exa.snu",
        ".str", ".lh2", ".alb", ".smb", ".dat", ".txt", ".lua", ".tree", ".shk",
        ".wav", ".ogg", ".mp3", ".flac", ".snr", ".ogv", ".mp4", ".avi", ".webm",
        ".png", ".dds", ".jpg", ".jpeg", ".bmp", ".tga", ".json", ".csv", ".yaml",
        ".yml", ".toml", ".fnt", ".srt", ".vtt", ".xml", ".amb", ".aub", ".ctb",
        ".mib", ".msb", ".rcm_b", ".sbk", ".toc", ".uix", ".ps3", ".itxd", ".bin",
        ".elf", ".snu", ".vp6", ".graph", ".txd", ".rws", ".dff", ".tob", ".inf",
        ".imb", ".vfb", ".bsp", ".mus"
    };

    public static string Identify(string name, string resource = "", ReadOnlySpan<byte> data = default)
    {
        name = name.Replace('\\', '/').ToLowerInvariant();
        string baseName = Path.GetFileName(name);

        if (data.Length >= 4)
        {
            if (data[0] == 0x7f && data[1] == (byte)'E' && data[2] == (byte)'L' && data[3] == (byte)'F') return ".elf";
            if (data.StartsWith("SCE\0"u8)) return ".bin";
        }

        if (string.Equals(resource, "UIE", StringComparison.OrdinalIgnoreCase))
            return ".dat.uie";

        if (data.Length >= 12)
        {
            if (data.Length >= 12 && data.Slice(8, 4).SequenceEqual("SimG"u8))
                return ".dat.simgroup";
            if (data.Length >= 8 && data.Slice(4, 4).SequenceEqual("SimG"u8))
                return ".dat.simgroup";
        }

        if (baseName.Equals("lighttoc", StringComparison.OrdinalIgnoreCase) ||
            baseName.Equals("streamsetconfig", StringComparison.OrdinalIgnoreCase))
            return baseName.ToLowerInvariant();

        string kind = "";
        foreach (var s in SuffixesDescending)
        {
            if (name.EndsWith(s, StringComparison.OrdinalIgnoreCase))
            {
                kind = s;
                break;
            }
        }

        if (kind == ".simgroup.dat") return ".dat.simgroup";

        if ((kind == "" || kind == ".dat" || kind == ".ps3") &&
            !string.IsNullOrEmpty(resource) &&
            ResourceKinds.TryGetValue(resource, out var mappedKind))
        {
            return mappedKind;
        }

        if (!string.IsNullOrEmpty(kind))
        {
            return kind == ".shk" ? ".shk.ps3" : kind;
        }

        if (data.Length >= 4)
        {
            if (data.StartsWith("2HCL"u8)) return ".lh2";
            if (data.StartsWith("FONT"u8)) return ".inf";
            if (data.StartsWith("1BOT"u8)) return ".tox.ps3";
            if (data.StartsWith("Hkx"u8)) return ".hkt.ps3";
            if (data.StartsWith("seqm"u8)) return ".xml.ps3";
            if (data.StartsWith("uixf"u8)) return ".uix";
            if (data.StartsWith("PFDx"u8)) return ".msb";
        }

        return "";
    }

    public static TreeNodeModel BuildTreeNode(string label, object? value)
    {
        var node = new TreeNodeModel { Label = label };

        if (value is Dictionary<string, object> dict)
        {
            foreach (var (k, v) in dict)
            {
                node.Children.Add(BuildTreeNode(k, v));
            }
        }
        else if (value is IEnumerable<object> list)
        {
            int idx = 0;
            foreach (var item in list)
            {
                node.Children.Add(BuildTreeNode($"[{idx++}]", item));
            }
        }
        else if (value != null)
        {
            node.Label = $"{label}: {value}";
        }

        return node;
    }
}

