using System.Buffers.Binary;
using System.Text;

namespace TheSimpsonsGame.FileViewer.Formats;

public class BnkClipEntry
{
    public int Index { get; set; }
    public string Name { get; set; } = string.Empty;
    public uint Offset { get; set; }
}

public class BnkData
{
    public uint PayloadSize { get; set; }
    public uint Version { get; set; }
    public uint BankAssetHash { get; set; }
    public uint TargetSkeletonHash { get; set; }
    public uint ClipCount { get; set; }
    public uint SecondaryCount { get; set; }
    public uint TableOffset { get; set; }
    public List<BnkClipEntry> Clips { get; } = new();
    public List<uint> Relocations { get; } = new();
}

public static class BnkParser
{
    public const uint ExpectedVersion = 0x09; // 9

    public static BnkData? Parse(byte[] data)
    {
        if (data.Length < 0x50) return null;

        ReadOnlySpan<byte> span = data;
        uint payloadSize = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(0, 4));
        uint version = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(4, 4));
        if (version != ExpectedVersion) return null;

        uint bankHash = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(8, 4));
        uint skeletonHash = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(12, 4));
        uint clipCount = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(0x20, 4));
        uint secCount = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(0x24, 4));
        uint tableOffset = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(0x28, 4));

        var bnk = new BnkData
        {
            PayloadSize = payloadSize,
            Version = version,
            BankAssetHash = bankHash,
            TargetSkeletonHash = skeletonHash,
            ClipCount = clipCount,
            SecondaryCount = secCount,
            TableOffset = tableOffset
        };

        // Extract clip names by scanning null-terminated ASCII strings
        var foundNames = new HashSet<string>(StringComparer.Ordinal);
        int cur = 0x50;
        int limit = (int)Math.Min((uint)data.Length, payloadSize > 0 ? payloadSize : (uint)data.Length);
        int clipIdx = 0;

        while (cur < limit - 4 && clipIdx < clipCount)
        {
            if (data[cur] >= 32 && data[cur] < 127)
            {
                int start = cur;
                while (cur < limit && data[cur] >= 32 && data[cur] < 127)
                {
                    cur++;
                }

                if (cur < limit && data[cur] == 0 && (cur - start >= 4))
                {
                    string str = Encoding.ASCII.GetString(data, start, cur - start).Trim();
                    // Clip names typically have letters/underscores and don't contain pure punctuation
                    if (str.Any(char.IsLetter) && !foundNames.Contains(str) && !str.StartsWith("___"))
                    {
                        foundNames.Add(str);
                        bnk.Clips.Add(new BnkClipEntry
                        {
                            Index = clipIdx++,
                            Name = str,
                            Offset = (uint)start
                        });
                    }
                }
            }
            cur++;
        }

        // Relocation table
        if (payloadSize > 0 && payloadSize < (uint)data.Length)
        {
            for (int r = (int)payloadSize; r + 4 <= data.Length; r += 4)
            {
                uint rel = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(r, 4));
                if (rel > 0) bnk.Relocations.Add(rel);
            }
        }

        return bnk;
    }

    public static TreeNodeModel ToTreeNode(BnkData bnk)
    {
        var root = new TreeNodeModel($"BNK Animation Bank (v{bnk.Version}, Bank 0x{bnk.BankAssetHash:08X}, Skeleton 0x{bnk.TargetSkeletonHash:08X})");
        var children = new List<TreeNodeModel>
        {
            new($"Target Skeleton Asset Hash: 0x{bnk.TargetSkeletonHash:08X} (Joins with .rcb.PS3)"),
            new($"Declared Clips: {bnk.ClipCount}, Secondary Tracks: {bnk.SecondaryCount}"),
            new($"Payload Size: 0x{bnk.PayloadSize:X} bytes, Pointer Relocations: {bnk.Relocations.Count}")
        };

        if (bnk.Clips.Count > 0)
        {
            var clipGroup = new TreeNodeModel($"Animation Clips ({bnk.Clips.Count} indexed)",
                bnk.Clips.Select(c => new TreeNodeModel($"[{c.Index}] \"{c.Name}\" at 0x{c.Offset:X}")).ToList());
            children.Add(clipGroup);
        }

        if (bnk.Relocations.Count > 0)
        {
            children.Add(new TreeNodeModel($"Pointer Relocations ({bnk.Relocations.Count} offsets)",
                bnk.Relocations.Take(50).Select((r, i) => new TreeNodeModel($"[{i}] Fixup at 0x{r:04X}")).ToList()));
        }

        root.Children = children;
        return root;
    }

    public static TableDataModel ToTable(BnkData bnk)
    {
        var model = new TableDataModel
        {
            Headers = new List<string> { "Index", "Clip Name", "String Offset" },
            Summary = $"BNK: {bnk.ClipCount} animation clips, Target Skeleton 0x{bnk.TargetSkeletonHash:08X}, {bnk.Relocations.Count} pointer relocations"
        };

        foreach (var clip in bnk.Clips)
        {
            model.Rows.Add(new List<string>
            {
                clip.Index.ToString(),
                clip.Name,
                $"0x{clip.Offset:04X}"
            });
        }

        return model;
    }
}

