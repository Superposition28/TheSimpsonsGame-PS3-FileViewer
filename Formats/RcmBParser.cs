using System.Buffers.Binary;

namespace TheSimpsonsGame.FileViewer.Formats;

public class RcmBRecord
{
    public int Index { get; set; }
    public uint EventHash { get; set; }
    public uint SpeakerId { get; set; }
    public uint SoundAlias1 { get; set; }
    public uint SoundAlias2 { get; set; }
    public uint SoundAlias3 { get; set; }
}

public class RcmBData
{
    public ushort Version { get; set; }
    public ushort RecordCount { get; set; }
    public uint HeaderSize { get; set; }
    public ushort Magic { get; set; }
    public ushort Reserved { get; set; }
    public uint TotalFileSize { get; set; }
    public List<RcmBRecord> Records { get; } = new();
}

public static class RcmBParser
{
    public const ushort ExpectedVersion = 1;
    public const ushort ExpectedMagic = 0xEFBE;

    public static RcmBData? Parse(byte[] data)
    {
        if (data.Length < 16) return null;

        ReadOnlySpan<byte> span = data;
        ushort version = BinaryPrimitives.ReadUInt16BigEndian(span.Slice(0, 2));
        ushort count = BinaryPrimitives.ReadUInt16BigEndian(span.Slice(2, 2));
        uint headerSize = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(4, 4));
        ushort magic = BinaryPrimitives.ReadUInt16BigEndian(span.Slice(8, 2));
        ushort reserved = BinaryPrimitives.ReadUInt16BigEndian(span.Slice(10, 2));
        uint totalFileSize = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(12, 4));

        if (version != ExpectedVersion || magic != ExpectedMagic) return null;
        if (totalFileSize != data.Length) return null;
        if (16 + count * 20 != data.Length) return null;

        var rcm = new RcmBData
        {
            Version = version,
            RecordCount = count,
            HeaderSize = headerSize,
            Magic = magic,
            Reserved = reserved,
            TotalFileSize = totalFileSize
        };

        for (int i = 0; i < count; i++)
        {
            int pos = 16 + i * 20;
            var recSpan = span.Slice(pos, 20);
            rcm.Records.Add(new RcmBRecord
            {
                Index = i,
                EventHash = BinaryPrimitives.ReadUInt32BigEndian(recSpan.Slice(0, 4)),
                SpeakerId = BinaryPrimitives.ReadUInt32BigEndian(recSpan.Slice(4, 4)),
                SoundAlias1 = BinaryPrimitives.ReadUInt32BigEndian(recSpan.Slice(8, 4)),
                SoundAlias2 = BinaryPrimitives.ReadUInt32BigEndian(recSpan.Slice(12, 4)),
                SoundAlias3 = BinaryPrimitives.ReadUInt32BigEndian(recSpan.Slice(16, 4))
            });
        }

        return rcm;
    }

    public static TableDataModel ToTable(RcmBData rcm)
    {
        var model = new TableDataModel
        {
            Headers = new List<string> { "Index", "Event Hash", "Speaker ID", "Sound Alias 1", "Sound Alias 2", "Sound Alias 3" },
            Summary = $"RCM_B: {rcm.Records.Count} audio bindings, Magic 0x{rcm.Magic:04X}, Version {rcm.Version}"
        };

        foreach (var rec in rcm.Records)
        {
            model.Rows.Add(new List<string>
            {
                rec.Index.ToString(),
                $"0x{rec.EventHash:08X}",
                $"0x{rec.SpeakerId:08X}",
                $"0x{rec.SoundAlias1:08X}",
                $"0x{rec.SoundAlias2:08X}",
                $"0x{rec.SoundAlias3:08X}"
            });
        }

        return model;
    }

    public static TreeNodeModel ToTreeNode(RcmBData rcm)
    {
        uint? primarySpeaker = rcm.Records.Count > 0 ? rcm.Records[0].SpeakerId : null;
        string speakerStr = primarySpeaker.HasValue ? $"Speaker 0x{primarySpeaker.Value:08X}" : "No records";
        var root = new TreeNodeModel($"RCM_B Motion Audio Binding (v{rcm.Version}, {rcm.RecordCount} entries, {speakerStr})");

        var children = new List<TreeNodeModel>
        {
            new($"Header: Size 0x{rcm.HeaderSize:X}, Magic 0x{rcm.Magic:04X}, Declared Total 0x{rcm.TotalFileSize:X} bytes"),
            new($"Record Count: {rcm.RecordCount} (Binary-search sorted)")
        };

        if (rcm.Records.Count > 0)
        {
            var recGroup = new TreeNodeModel($"Audio Bindings ({rcm.Records.Count} entries)",
                rcm.Records.Select(r => new TreeNodeModel(
                    $"[{r.Index}] Event 0x{r.EventHash:08X} -> Speaker 0x{r.SpeakerId:08X} (Aliases: 0x{r.SoundAlias1:08X}, 0x{r.SoundAlias2:08X}, 0x{r.SoundAlias3:08X})")).ToList());
            children.Add(recGroup);
        }

        root.Children = children;
        return root;
    }
}

