using System.Buffers.Binary;
using System.Text;

namespace TheSimpsonsGame.FileViewer.Formats;

public class CtbCueEntry
{
    public int Index { get; set; }
    public byte Tag { get; set; }
    public byte Subtype { get; set; }
    public byte Weight { get; set; }
    public byte AliasCount { get; set; }
    public string EventName { get; set; } = string.Empty;
    public uint StringOffset { get; set; }
    public uint SoundAliasOffset { get; set; }
    public uint TargetHash { get; set; }
    public float Volume { get; set; } = 1.0f;
    public float PitchOrPan { get; set; }
    public float MinDistance { get; set; }
    public float MaxDistance { get; set; }
    public List<uint> SoundAliases { get; } = new();
}

public class CtbData
{
    public ushort Version { get; set; }
    public ushort Subtype { get; set; }
    public ushort CueCount { get; set; }
    public ushort CategoryFlags { get; set; }
    public uint HeaderParam { get; set; }
    public uint AssetHash { get; set; }
    public float DefaultGain { get; set; } = 1.0f;
    public List<CtbCueEntry> Cues { get; } = new();
}

public static class CtbParser
{
    public const ushort ExpectedVersion = 6;

    public static CtbData? Parse(byte[] data)
    {
        if (data.Length < 0x38) return null;

        ReadOnlySpan<byte> span = data;
        ushort version = BinaryPrimitives.ReadUInt16BigEndian(span.Slice(0, 2));
        if (version != ExpectedVersion) return null;

        ushort subtype = BinaryPrimitives.ReadUInt16BigEndian(span.Slice(2, 2));
        ushort cueCount = BinaryPrimitives.ReadUInt16BigEndian(span.Slice(0x10, 2));
        ushort catFlags = BinaryPrimitives.ReadUInt16BigEndian(span.Slice(0x12, 2));
        uint headerParam = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(0x14, 4));
        uint assetHash = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(0x18, 4));
        float defaultGain = BinaryPrimitives.ReadSingleBigEndian(span.Slice(0x1C, 4));

        var ctb = new CtbData
        {
            Version = version,
            Subtype = subtype,
            CueCount = cueCount,
            CategoryFlags = catFlags,
            HeaderParam = headerParam,
            AssetHash = assetHash,
            DefaultGain = defaultGain
        };

        for (int i = 0; i < cueCount; i++)
        {
            int pos = 0x38 + i * 44;
            if (pos + 12 > data.Length) break;

            byte tag = data[pos];
            byte sub = data[pos + 1];
            byte weight = data[pos + 2];
            byte aliasCount = data[pos + 3];
            uint strOff = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(pos + 4, 4));
            uint idOff = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(pos + 8, 4));

            string name = string.Empty;
            if (strOff < (uint)data.Length)
            {
                int end = (int)strOff;
                while (end < data.Length && data[end] != 0) end++;
                if (end > (int)strOff)
                {
                    name = Encoding.ASCII.GetString(data, (int)strOff, end - (int)strOff);
                }
            }

            var cue = new CtbCueEntry
            {
                Index = i,
                Tag = tag,
                Subtype = sub,
                Weight = weight,
                AliasCount = aliasCount,
                EventName = name,
                StringOffset = strOff,
                SoundAliasOffset = idOff
            };

            if (pos + 40 <= data.Length && (i < cueCount - 1 || pos + 40 <= (int)idOff))
            {
                cue.TargetHash = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(pos + 12, 4));
                cue.Volume = BinaryPrimitives.ReadSingleBigEndian(span.Slice(pos + 16, 4));
                cue.PitchOrPan = BinaryPrimitives.ReadSingleBigEndian(span.Slice(pos + 20, 4));
                cue.MinDistance = BinaryPrimitives.ReadSingleBigEndian(span.Slice(pos + 24, 4));
                cue.MaxDistance = BinaryPrimitives.ReadSingleBigEndian(span.Slice(pos + 28, 4));
            }

            for (int a = 0; a < aliasCount; a++)
            {
                int aPos = (int)idOff + a * 4;
                if (aPos + 4 <= data.Length)
                {
                    uint aliasId = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(aPos, 4));
                    cue.SoundAliases.Add(aliasId);
                }
            }

            ctb.Cues.Add(cue);
        }

        return ctb;
    }

    public static TableDataModel ToTable(CtbData ctb)
    {
        var model = new TableDataModel
        {
            Headers = new List<string> { "Index", "Tag", "Event Cue Name", "Target Hash", "Volume", "Distances", "Sound Aliases" },
            Summary = $"CTB: {ctb.Cues.Count} event cues, Asset 0x{ctb.AssetHash:08X}, Gain {ctb.DefaultGain:F1}, Version {ctb.Version}"
        };

        foreach (var cue in ctb.Cues)
        {
            char tagChar = cue.Tag >= 32 && cue.Tag < 127 ? (char)cue.Tag : '.';
            string aliasesStr = cue.SoundAliases.Count switch
            {
                0 => "none",
                <= 3 => string.Join(", ", cue.SoundAliases.Select(a => $"0x{a:08X}")),
                _ => $"{string.Join(", ", cue.SoundAliases.Take(3).Select(a => $"0x{a:08X}"))} (+{cue.SoundAliases.Count - 3} more)"
            };

            model.Rows.Add(new List<string>
            {
                cue.Index.ToString(),
                $"0x{cue.Tag:02X} ('{tagChar}')",
                cue.EventName,
                $"0x{cue.TargetHash:08X}",
                cue.Volume.ToString("F1"),
                $"{cue.MinDistance:F0}..{cue.MaxDistance:F0}",
                aliasesStr
            });
        }

        return model;
    }

    public static TreeNodeModel ToTreeNode(CtbData ctb)
    {
        var root = new TreeNodeModel($"CTB Audio Control Table (v{ctb.Version}, {ctb.Cues.Count} event cues, Asset 0x{ctb.AssetHash:08X}, Gain {ctb.DefaultGain:F1})");

        var children = new List<TreeNodeModel>
        {
            new($"Header: Version {ctb.Version}, Subtype 0x{ctb.Subtype:X4}, Asset 0x{ctb.AssetHash:08X}, Gain {ctb.DefaultGain:F1}"),
            new($"Event Cues: {ctb.Cues.Count} declared (44-byte record stride)")
        };

        if (ctb.Cues.Count > 0)
        {
            var cueNodes = new List<TreeNodeModel>();
            foreach (var cue in ctb.Cues)
            {
                char tagChar = cue.Tag >= 32 && cue.Tag < 127 ? (char)cue.Tag : '.';
                var cueNode = new TreeNodeModel($"[{cue.Index}] \"{cue.EventName}\" (Tag 0x{cue.Tag:02X} '{tagChar}', Vol {cue.Volume:F1}, {cue.SoundAliases.Count} aliases)");
                var cueDetails = new List<TreeNodeModel>
                {
                    new($"Target / Speaker Hash: 0x{cue.TargetHash:08X}"),
                    new($"3D Attenuation: Min {cue.MinDistance:F1}, Max {cue.MaxDistance:F1}, Pitch/Pan {cue.PitchOrPan:F1}"),
                    new($"Offsets: String at 0x{cue.StringOffset:04X}, Aliases at 0x{cue.SoundAliasOffset:04X}")
                };

                if (cue.SoundAliases.Count > 0)
                {
                    var aliasList = new TreeNodeModel($"Sound Aliases ({cue.SoundAliases.Count} entries linking to .alb)",
                        cue.SoundAliases.Select((a, idx) => new TreeNodeModel($"[{idx}] Alias 0x{a:08X}")).ToList());
                    cueDetails.Add(aliasList);
                }

                cueNode.Children = cueDetails;
                cueNodes.Add(cueNode);
            }
            children.Add(new TreeNodeModel($"Cue Triggers ({ctb.Cues.Count} items)", cueNodes));
        }

        root.Children = children;
        return root;
    }
}

