using System.Buffers.Binary;
using System.Text;

namespace TheSimpsonsGame.FileViewer.Formats;

public class VfbEntryData
{
    public int Index { get; set; }
    public uint Offset { get; set; }
    public uint DurationMs { get; set; }
    public uint ParameterFlags { get; set; }
    public float Intensity { get; set; }
}

public class VfbData
{
    public const uint ExpectedVersion = 0x06;

    public string EffectName { get; set; } = string.Empty;
    public uint Version { get; set; }
    public uint EntryCount { get; set; }
    public uint PayloadSize { get; set; }
    public List<VfbEntryData> Entries { get; } = new();
}

public static class VfbParser
{
    public const uint ExpectedVersion = 0x06;

    public static VfbData? Parse(byte[] data)
    {
        if (data.Length < 0x20) return null;

        ReadOnlySpan<byte> span = data;

        // 32-byte global header
        int nameEnd = 0;
        while (nameEnd < 16 && data[nameEnd] != 0) nameEnd++;
        string effectName = Encoding.ASCII.GetString(data, 0, nameEnd).Trim();

        uint version = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(0x10, 4));
        if (version != ExpectedVersion && version != 0) return null;

        uint entryCount = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(0x14, 4));
        uint payloadSize = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(0x18, 4));

        var vfb = new VfbData
        {
            EffectName = effectName,
            Version = version,
            EntryCount = entryCount,
            PayloadSize = payloadSize
        };

        // Offset table entries (each 28 bytes) starting at offset 0x20
        int pos = 0x20;
        for (int i = 0; i < entryCount && pos + 28 <= data.Length; i++)
        {
            uint offset = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(pos, 4));
            uint duration = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(pos + 4, 4));
            uint flags = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(pos + 8, 4));
            float intensity = BinaryPrimitives.ReadSingleBigEndian(span.Slice(pos + 12, 4));

            vfb.Entries.Add(new VfbEntryData
            {
                Index = i,
                Offset = offset,
                DurationMs = duration,
                ParameterFlags = flags,
                Intensity = intensity
            });

            pos += 28;
        }

        return vfb;
    }

    public static TreeNodeModel ToTreeNode(VfbData vfb)
    {
        var root = new TreeNodeModel($"VFB Visual Effects Bundle (\"{vfb.EffectName}\", v{vfb.Version}, {vfb.Entries.Count} Emitters/Blocks)");
        var children = new List<TreeNodeModel>
        {
            new($"Effect Identifier: \"{vfb.EffectName}\""),
            new($"Declared Entries: {vfb.EntryCount}, Stated Payload: {vfb.PayloadSize:N0} bytes")
        };

        if (vfb.Entries.Count > 0)
        {
            var entGroup = new TreeNodeModel($"Effect Sub-Blocks ({vfb.Entries.Count})",
                vfb.Entries.Select(e => new TreeNodeModel($"[{e.Index}] Offset=0x{e.Offset:X4}, Duration={e.DurationMs}ms, Intensity={e.Intensity:F2}, Flags=0x{e.ParameterFlags:X8}")).ToList());
            children.Add(entGroup);
        }

        root.Children = children;
        return root;
    }

    public static TableDataModel ToTable(VfbData vfb)
    {
        var model = new TableDataModel
        {
            Headers = new List<string> { "Index", "Offset", "Duration (ms)", "Intensity", "Flags" },
            Summary = $"VFB: \"{vfb.EffectName}\", {vfb.Entries.Count} effect blocks, {vfb.PayloadSize:N0} bytes payload"
        };

        foreach (var e in vfb.Entries)
        {
            model.Rows.Add(new List<string>
            {
                e.Index.ToString(),
                $"0x{e.Offset:04X}",
                $"{e.DurationMs} ms",
                $"{e.Intensity:F2}",
                $"0x{e.ParameterFlags:X8}"
            });
        }

        return model;
    }
}
