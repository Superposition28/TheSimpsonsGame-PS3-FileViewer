using System.Buffers.Binary;
using System.Text;

namespace TheSimpsonsGame.FileViewer.Formats;

public static class MiscParsers
{
    // --- LightTOC ---
    public static List<float> ParseLightToc(byte[] data)
    {
        var floats = new List<float>();
        if (data.Length >= 128 && data.AsSpan(0, 4).SequenceEqual(new byte[] { 0x40, 0xF2, 0x00, 0x01 }))
        {
            ReadOnlySpan<byte> span = data.AsSpan(16);
            for (int i = 0; i < 28 && (i + 1) * 4 <= span.Length; i++)
            {
                floats.Add(BinaryPrimitives.ReadSingleBigEndian(span.Slice(i * 4, 4)));
            }
        }
        return floats;
    }

    // --- CEC ---
    public static TableDataModel ParseCec(byte[] data)
    {
        var model = new TableDataModel
        {
            Headers = new List<string> { "Index", "ConfigID", "Flags", "EventCount" }
        };

        if (data.Length < 16)
        {
            model.Summary = "Short CEC header";
            return model;
        }

        ReadOnlySpan<byte> span = data;
        ushort count = BinaryPrimitives.ReadUInt16BigEndian(span.Slice(6, 2));

        int pos = 16;
        for (int i = 0; i < count && pos + 8 <= data.Length; i++)
        {
            uint configId = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(pos, 4));
            ushort flags = BinaryPrimitives.ReadUInt16BigEndian(span.Slice(pos + 4, 2));
            ushort events = BinaryPrimitives.ReadUInt16BigEndian(span.Slice(pos + 6, 2));

            model.Rows.Add(new List<string>
            {
                i.ToString(),
                $"0x{configId:08X}",
                $"0x{flags:X4}",
                events.ToString()
            });

            pos += 8;
        }

        model.Summary = $"CEC: {count} controller configurations";
        return model;
    }

    // --- SHK ---
    public static TableDataModel ParseShk(byte[] data)
    {
        var model = new TableDataModel
        {
            Headers = new List<string> { "Index", "Command", "Time", "Magnitude" }
        };

        if (data.Length < 12)
        {
            model.Summary = "Short SHK header";
            return model;
        }

        ReadOnlySpan<byte> span = data;
        short count = BinaryPrimitives.ReadInt16BigEndian(span.Slice(6, 2));

        int pos = 12;
        for (int i = 0; i < count && pos + 4 <= data.Length; i++)
        {
            byte cmd = data[pos];
            byte time = data[pos + 1];
            short mag = BinaryPrimitives.ReadInt16BigEndian(span.Slice(pos + 2, 2));

            model.Rows.Add(new List<string>
            {
                i.ToString(),
                $"0x{cmd:X2}",
                time.ToString(),
                mag.ToString()
            });

            pos += 4;
        }

        model.Summary = $"SHK: {count} haptic commands";
        return model;
    }

    // --- TOB / TOX ---
    public static TableDataModel ParseTob(byte[] data)
    {
        var model = new TableDataModel
        {
            Headers = new List<string> { "Index", "StringID", "StartTime", "EndTime" }
        };

        if (data.Length < 16)
        {
            model.Summary = "Short TOB header";
            return model;
        }

        ReadOnlySpan<byte> span = data;
        uint count = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(8, 4));

        int pos = 16;
        for (int i = 0; i < count && pos + 12 <= data.Length; i++)
        {
            uint sid = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(pos, 4));
            float start = BinaryPrimitives.ReadSingleBigEndian(span.Slice(pos + 4, 4));
            float end = BinaryPrimitives.ReadSingleBigEndian(span.Slice(pos + 8, 4));

            model.Rows.Add(new List<string>
            {
                i.ToString(),
                $"{sid:08X}",
                $"{start:F2}s",
                $"{end:F2}s"
            });

            pos += 12;
        }

        model.Summary = $"TOB: {count} subtitle cues";
        return model;
    }

    // --- Navigation Graph ---
    public static TreeNodeModel ParseGraph(byte[] data)
    {
        var root = new TreeNodeModel("Navigation Graph");
        if (data.Length < 40)
        {
            root.Label = "Short Navigation Graph header";
            return root;
        }

        ReadOnlySpan<byte> span = data;
        ushort nodes = BinaryPrimitives.ReadUInt16BigEndian(span.Slice(12, 2));
        ushort edges = BinaryPrimitives.ReadUInt16BigEndian(span.Slice(14, 2));
        uint nodeOffset = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(32, 4));
        uint edgeOffset = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(36, 4));

        root.Label = $"Navigation Graph: {nodes} Nodes, {edges} Edges";

        var children = new List<TreeNodeModel>();

        if (nodeOffset > 0 && nodeOffset + (nodes * 32) <= (uint)data.Length)
        {
            var nodeGroup = new TreeNodeModel($"Nodes ({nodes})");
            var nList = new List<TreeNodeModel>();
            int limit = Math.Min((int)nodes, 100);

            for (int i = 0; i < limit; i++)
            {
                int pos = (int)nodeOffset + (i * 32);
                float x = BinaryPrimitives.ReadSingleBigEndian(span.Slice(pos, 4));
                float y = BinaryPrimitives.ReadSingleBigEndian(span.Slice(pos + 4, 4));
                float z = BinaryPrimitives.ReadSingleBigEndian(span.Slice(pos + 8, 4));
                nList.Add(new TreeNodeModel($"Node {i}: Position=({x:F2}, {y:F2}, {z:F2})"));
            }

            if (nodes > limit) nList.Add(new TreeNodeModel($"... and {nodes - limit} more nodes"));
            nodeGroup.Children = nList;
            children.Add(nodeGroup);
        }

        if (edgeOffset > 0 && edgeOffset + (edges * 16) <= (uint)data.Length)
        {
            children.Add(new TreeNodeModel($"Edges ({edges}) at offset 0x{edgeOffset:X}"));
        }

        root.Children = children;
        return root;
    }

    // --- MetaModel ---
    public static TreeNodeModel ParseMetaModel(byte[] data)
    {
        var root = new TreeNodeModel("MetaModel");
        if (data.Length < 24) return root;

        ReadOnlySpan<byte> span = data;
        uint count = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(0, 4));
        root.Label = $"MetaModel: {count} Asset Table Entries";

        var children = new List<TreeNodeModel>();
        int pos = 4;
        for (int i = 0; i < count && pos + 16 <= data.Length; i++)
        {
            string guid = Convert.ToHexString(data.AsSpan(pos, 16));
            children.Add(new TreeNodeModel($"Asset {i}: GUID={guid}"));
            pos += 16;
        }

        root.Children = children;
        return root;
    }

    // --- Havok 4.1 ---
    public static TreeNodeModel ParseHavok(byte[] data)
    {
        var root = new TreeNodeModel("Havok 4.1 Packfile");
        if (data.Length < 80 || !data.AsSpan(0, 4).SequenceEqual("Hkx\x10"u8))
        {
            root.Label = "Invalid Havok packfile signature";
            return root;
        }

        ReadOnlySpan<byte> span = data;
        uint version = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(28, 4));
        uint sectionCount = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(36, 4));

        root.Label = $"Havok 4.1 Packfile (v{version}, {sectionCount} Sections)";
        var children = new List<TreeNodeModel>();

        for (int i = 0; i < sectionCount && 80 + (i * 48) <= data.Length; i++)
        {
            int sPos = 80 + (i * 48);
            string name = Encoding.ASCII.GetString(data, sPos, 19).TrimEnd('\0');
            uint start = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(sPos + 20, 4));
            children.Add(new TreeNodeModel($"Section '{name}': PackfileRelativeStart=0x{start:X}"));
        }

        root.Children = children;
        return root;
    }

    // --- MSB ---
    public static TreeNodeModel ParseMsb(byte[] data)
    {
        var root = new TreeNodeModel("Pathfinder MSB");
        if (data.Length < 0x54) return root;

        ReadOnlySpan<byte> span = data;
        uint mapSize = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(0x24, 4));
        uint signature = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(0x2C, 4));

        root.Label = $"Pathfinder MSB (Sig=0x{signature:X8}, MapSize=0x{mapSize:X})";
        var children = new List<TreeNodeModel>();

        // Look for paired MUS filename literal
        for (int i = 0; i < Math.Min(data.Length - 4, 0x1000); i++)
        {
            if (data[i] == '.' && (i + 4 <= data.Length) &&
                (data[i + 1] == 'm' || data[i + 1] == 'M') &&
                (data[i + 2] == 'u' || data[i + 2] == 'U') &&
                (data[i + 3] == 's' || data[i + 3] == 'S'))
            {
                int start = i;
                while (start > 0 && data[start - 1] > 32 && data[start - 1] < 127)
                    start--;
                string musName = Encoding.ASCII.GetString(data, start, i + 4 - start);
                children.Add(new TreeNodeModel($"Paired MUS File: '{musName}'"));
                break;
            }
        }

        root.Children = children;
        return root;
    }
}

