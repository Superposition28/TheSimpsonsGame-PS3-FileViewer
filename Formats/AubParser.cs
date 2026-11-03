using System.Buffers.Binary;
using System.Text;

namespace TheSimpsonsGame.FileViewer.Formats;

public class AubBusEntry
{
    public int Index { get; set; }
    public uint Offset { get; set; }
    public string BusName { get; set; } = string.Empty;
    public string Category { get; set; } = string.Empty;
    public uint Parameter { get; set; }
    public float ParameterFloat { get; set; }
}

public class AubDspNode
{
    public uint Offset { get; set; }
    public string Name { get; set; } = string.Empty;
}

public class AubData
{
    public const string ExpectedMagic = "SSFX";

    public string Magic { get; set; } = string.Empty;
    public uint BusCount { get; set; }
    public uint CategoryCount { get; set; }
    public List<AubBusEntry> Buses { get; } = new();
    public List<AubDspNode> DspNodes { get; } = new();
}

public static class AubParser
{
    public static AubData? Parse(byte[] data)
    {
        if (data.Length < 0x80) return null;

        ReadOnlySpan<byte> span = data;
        string magic = Encoding.ASCII.GetString(data, 0x1C, 4);
        if (magic != AubData.ExpectedMagic) return null;

        uint busCount = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(0x10, 4));
        uint catCount = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(0x14, 4));

        var aub = new AubData
        {
            Magic = magic,
            BusCount = busCount,
            CategoryCount = catCount
        };

        // Parse 100-byte bus entries
        int pos = 0x80;
        for (int i = 0; i < busCount && pos + 100 <= data.Length; i++)
        {
            int busNameEnd = pos;
            while (busNameEnd < pos + 64 && data[busNameEnd] != 0) busNameEnd++;
            string busName = Encoding.ASCII.GetString(data, pos, busNameEnd - pos).Trim();

            int catPos = pos + 64;
            int catNameEnd = catPos;
            while (catNameEnd < catPos + 32 && data[catNameEnd] != 0) catNameEnd++;
            string catName = Encoding.ASCII.GetString(data, catPos, catNameEnd - catPos).Trim();

            uint param = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(pos + 96, 4));
            float paramFloat = BinaryPrimitives.ReadSingleBigEndian(span.Slice(pos + 96, 4));

            aub.Buses.Add(new AubBusEntry
            {
                Index = i,
                Offset = (uint)pos,
                BusName = busName,
                Category = catName,
                Parameter = param,
                ParameterFloat = paramFloat
            });

            pos += 100;
        }

        // Scan DSP nodes and reverb zones after the bus table
        int cur = 0x80 + (int)(busCount * 100);
        while (cur + 64 <= data.Length)
        {
            int namePos = cur + 20;
            int nameEnd = namePos;
            while (nameEnd < cur + 64 && data[nameEnd] != 0) nameEnd++;

            if (nameEnd - namePos >= 3)
            {
                string name = Encoding.ASCII.GetString(data, namePos, nameEnd - namePos).Trim();
                if (name.Any(char.IsLetter))
                {
                    aub.DspNodes.Add(new AubDspNode
                    {
                        Offset = (uint)cur,
                        Name = name
                    });
                    cur += 64;
                    continue;
                }
            }
            cur += 4;
        }

        return aub;
    }

    public static TreeNodeModel ToTreeNode(AubData aub)
    {
        var root = new TreeNodeModel($"AUB Audio User Bus ({aub.Buses.Count} Mix Buses, {aub.CategoryCount} Categories, {aub.DspNodes.Count} DSP Nodes)");
        var children = new List<TreeNodeModel>
        {
            new($"Engine Magic: \"{aub.Magic}\" (Simpsons SoundFX)"),
            new($"Declared Mix Buses: {aub.BusCount}, Parent Categories: {aub.CategoryCount}")
        };

        // Group buses by Category
        var catGroups = aub.Buses.GroupBy(b => string.IsNullOrEmpty(b.Category) ? "Uncategorized" : b.Category);
        var busTree = new TreeNodeModel($"Mix Buses ({aub.Buses.Count})");
        foreach (var group in catGroups)
        {
            var catNode = new TreeNodeModel($"Category \"{group.Key}\" ({group.Count()} Buses)",
                group.Select(b => new TreeNodeModel($"[{b.Index}] \"{b.BusName}\" (Param=0x{b.Parameter:08X})")).ToList());
            busTree.Children.Add(catNode);
        }
        children.Add(busTree);

        if (aub.DspNodes.Count > 0)
        {
            var dspGroup = new TreeNodeModel($"Master DSP Graph & Zones ({aub.DspNodes.Count} Nodes)",
                aub.DspNodes.Select(n => new TreeNodeModel($"\"{n.Name}\" at 0x{n.Offset:X4}")).ToList());
            children.Add(dspGroup);
        }

        root.Children = children;
        return root;
    }

    public static TableDataModel ToTable(AubData aub)
    {
        var model = new TableDataModel
        {
            Headers = new List<string> { "Index", "Bus Name", "Category", "Parameter (Hex)", "Parameter (Float)" },
            Summary = $"AUB: {aub.Buses.Count} audio buses across {aub.CategoryCount} categories, {aub.DspNodes.Count} DSP nodes"
        };

        foreach (var b in aub.Buses)
        {
            model.Rows.Add(new List<string>
            {
                b.Index.ToString(),
                b.BusName,
                string.IsNullOrEmpty(b.Category) ? "(none)" : b.Category,
                $"0x{b.Parameter:08X}",
                Math.Abs(b.ParameterFloat) < 10000 ? $"{b.ParameterFloat:F2}" : "-"
            });
        }

        return model;
    }
}

