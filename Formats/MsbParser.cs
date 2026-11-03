using System.Buffers.Binary;
using System.Text;

namespace TheSimpsonsGame.FileViewer.Formats;

public class MsbEventData
{
    public string Name { get; set; } = string.Empty;
    public uint Id { get; set; }
}

public class MsbPartData
{
    public string Name { get; set; } = string.Empty;
    public int EntryNode { get; set; }
}

public class MsbData
{
    public const uint ExpectedSignature = 0x38071778;
    public const uint PfdxMagic = 0x50464478; // "PFDx"

    public uint PfdMapSize { get; set; }
    public uint FormatSignature { get; set; }
    public string PairedMusFilename { get; set; } = string.Empty;
    public uint PfdVersion { get; set; }
    public uint[] SectionOffsets { get; set; } = Array.Empty<uint>();
    public uint MusFileId { get; set; }

    public List<MsbEventData> Events { get; } = new();
    public List<MsbPartData> Parts { get; } = new();
    public Dictionary<string, string> Defines { get; } = new(StringComparer.OrdinalIgnoreCase);
}

public static class MsbParser
{
    public static MsbData? Parse(byte[] data)
    {
        if (data.Length < 0x54) return null;

        ReadOnlySpan<byte> span = data;

        // Outer Pathfinder header (80 bytes, 0x00..0x4F)
        uint pfdMapSize = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(0x24, 4));
        uint signature = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(0x2C, 4));

        int nameEnd = 0x30;
        while (nameEnd < 0x50 && span[nameEnd] != 0) nameEnd++;
        string pairedMus = Encoding.ASCII.GetString(span.Slice(0x30, nameEnd - 0x30)).Trim();

        // PFDx Chunk starts at offset 0x50
        uint magic = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(0x50, 4));
        if (magic != MsbData.PfdxMagic) return null;

        uint pfdVersion = 0;
        uint[] sections = new uint[9];
        uint musFileId = 0;

        if (span.Length >= 0x7C)
        {
            pfdVersion = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(0x54, 4));
            for (int i = 0; i < 9; i++)
            {
                sections[i] = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(0x58 + (i * 4), 4));
            }

            int s7Offset = 0x50 + (int)sections[7];
            if (s7Offset + 20 <= data.Length)
            {
                musFileId = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(s7Offset + 16, 4));
            }
        }

        var msb = new MsbData
        {
            PfdMapSize = pfdMapSize,
            FormatSignature = signature,
            PairedMusFilename = pairedMus,
            PfdVersion = pfdVersion,
            SectionOffsets = sections,
            MusFileId = musFileId
        };

        // Plaintext symbol trailer at 0x50 + pfdMapSize
        int trailerOffset = 0x50 + (int)pfdMapSize;
        if (trailerOffset < data.Length)
        {
            string trailerText = Encoding.Latin1.GetString(span[trailerOffset..]);
            string[] lines = trailerText.Replace("\r\n", "\r").Replace('\n', '\r').Split('\r', StringSplitOptions.RemoveEmptyEntries);

            string currentSection = "";
            foreach (var rawLine in lines)
            {
                string line = rawLine.Trim();
                if (string.IsNullOrEmpty(line)) continue;

                if (line.StartsWith("numevents", StringComparison.OrdinalIgnoreCase))
                {
                    currentSection = "events";
                    continue;
                }
                if (line.StartsWith("numparts", StringComparison.OrdinalIgnoreCase))
                {
                    currentSection = "parts";
                    continue;
                }
                if (line.StartsWith("numdefines", StringComparison.OrdinalIgnoreCase))
                {
                    currentSection = "defines";
                    continue;
                }

                if (currentSection == "events")
                {
                    int colon = line.IndexOf(':');
                    if (colon > 0 && colon + 1 < line.Length)
                    {
                        string evName = line[..colon].Trim();
                        string evIdStr = line[(colon + 1)..].Trim();
                        uint.TryParse(evIdStr, out uint evId);
                        msb.Events.Add(new MsbEventData { Name = evName, Id = evId });
                    }
                }
                else if (currentSection == "parts")
                {
                    int entryIdx = line.IndexOf("entry node =", StringComparison.OrdinalIgnoreCase);
                    if (entryIdx >= 0)
                    {
                        string partName = line[..entryIdx].Trim();
                        string nodeStr = line[(entryIdx + "entry node =".Length)..].Trim();
                        int.TryParse(nodeStr, out int node);
                        msb.Parts.Add(new MsbPartData { Name = partName, EntryNode = node });
                    }
                    else
                    {
                        msb.Parts.Add(new MsbPartData { Name = line, EntryNode = -1 });
                    }
                }
                else if (currentSection == "defines")
                {
                    int space = line.IndexOfAny(new[] { ' ', '\t' });
                    if (space > 0)
                    {
                        string key = line[..space].Trim();
                        string val = line[space..].Trim();
                        msb.Defines[key] = val;
                    }
                }
            }
        }

        return msb;
    }

    public static TreeNodeModel ToTreeNode(MsbData msb)
    {
        var root = new TreeNodeModel($"Pathfinder MSB (Paired MUS: '{msb.PairedMusFilename}', PFD v{msb.PfdVersion}, MusFileId 0x{msb.MusFileId:08X})");
        var children = new List<TreeNodeModel>
        {
            new($"Outer Wrapper: MapSize=0x{msb.PfdMapSize:X}, Signature=0x{msb.FormatSignature:08X}"),
            new($"Paired MUS Container: \"{msb.PairedMusFilename}\" (Header Checksum 0x{msb.MusFileId:08X})")
        };

        var secGroup = new TreeNodeModel("PFDx Section Offsets (S0..S8)");
        for (int i = 0; i < msb.SectionOffsets.Length; i++)
        {
            secGroup.Children.Add(new TreeNodeModel($"S{i}: Offset 0x{msb.SectionOffsets[i]:X} (Abs: 0x{0x50 + msb.SectionOffsets[i]:X})"));
        }
        children.Add(secGroup);

        if (msb.Events.Count > 0)
        {
            children.Add(new TreeNodeModel($"Interactive Events ({msb.Events.Count})",
                msb.Events.Select(e => new TreeNodeModel($"Event ID {e.Id}: \"{e.Name}\"")).ToList()));
        }

        if (msb.Parts.Count > 0)
        {
            children.Add(new TreeNodeModel($"Conductor Parts ({msb.Parts.Count})",
                msb.Parts.Select(p => new TreeNodeModel($"Part \"{p.Name}\" (EntryNode={p.EntryNode})")).ToList()));
        }

        if (msb.Defines.Count > 0)
        {
            children.Add(new TreeNodeModel($"Defines / Track Masks ({msb.Defines.Count})",
                msb.Defines.Select(kv => new TreeNodeModel($"{kv.Key} = {kv.Value}")).ToList()));
        }

        root.Children = children;
        return root;
    }

    public static TableDataModel ToTable(MsbData msb)
    {
        var model = new TableDataModel
        {
            Headers = new List<string> { "Type", "ID / Node", "Name / Value" },
            Summary = $"MSB: {msb.Events.Count} events, {msb.Parts.Count} parts, {msb.Defines.Count} defines, Paired MUS: '{msb.PairedMusFilename}'"
        };

        foreach (var ev in msb.Events)
        {
            model.Rows.Add(new List<string> { "Event", ev.Id.ToString(), ev.Name });
        }

        foreach (var pt in msb.Parts)
        {
            model.Rows.Add(new List<string> { "Part", pt.EntryNode.ToString(), pt.Name });
        }

        foreach (var df in msb.Defines)
        {
            model.Rows.Add(new List<string> { "Define", df.Key, df.Value });
        }

        return model;
    }
}

