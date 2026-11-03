using System.Buffers.Binary;
using System.Text;

namespace TheSimpsonsGame.FileViewer.Formats;

public class RcbComponentEntry
{
    public int Index { get; set; }
    public uint HashId { get; set; }
    public string Name { get; set; } = string.Empty;
    public uint BoneCount { get; set; }
    public uint PtrTransform { get; set; }
    public uint PtrMatrices { get; set; }
    public uint PtrBounds { get; set; }
    public float[]? TransformMatrix { get; set; } // 16 floats (4x4)
}

public class RcbData
{
    public uint PayloadSize { get; set; }
    public uint Version { get; set; }
    public uint AssetHash { get; set; }
    public uint EntryCount { get; set; }
    public uint TableOffset { get; set; }
    public List<RcbComponentEntry> Entries { get; } = new();
    public List<uint> Relocations { get; } = new();
}

public static class RcbParser
{
    public const uint ExpectedVersion = 0x17; // 23

    public static RcbData? Parse(byte[] data)
    {
        if (data.Length < 0x60) return null;

        ReadOnlySpan<byte> span = data;
        uint payloadSize = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(0, 4));
        uint version = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(4, 4));
        if (version != ExpectedVersion) return null;

        uint assetHash = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(8, 4));
        uint entryCount = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(0x18, 4));
        uint tableOffset = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(0x1C, 4));

        var rcb = new RcbData
        {
            PayloadSize = payloadSize,
            Version = version,
            AssetHash = assetHash,
            EntryCount = entryCount,
            TableOffset = tableOffset
        };

        // Parse component slice records (each 24 bytes)
        for (int i = 0; i < entryCount; i++)
        {
            int pos = (int)tableOffset + (i * 24);
            if (pos + 24 > data.Length) break;

            uint hashId = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(pos, 4));
            uint namePtr = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(pos + 4, 4));
            uint boneCount = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(pos + 8, 4));
            uint ptrTransform = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(pos + 12, 4));
            uint ptrMatrices = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(pos + 16, 4));
            uint ptrBounds = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(pos + 20, 4));

            string name = "";
            if (namePtr > 0 && namePtr < (uint)data.Length)
            {
                int end = (int)namePtr;
                while (end < data.Length && data[end] != 0) end++;
                name = Encoding.ASCII.GetString(data, (int)namePtr, end - (int)namePtr).Trim();
            }

            var entry = new RcbComponentEntry
            {
                Index = i,
                HashId = hashId,
                Name = name,
                BoneCount = boneCount,
                PtrTransform = ptrTransform,
                PtrMatrices = ptrMatrices,
                PtrBounds = ptrBounds
            };

            // Read 4x4 matrix if available
            if (ptrMatrices > 0 && ptrMatrices + 64 <= (uint)data.Length)
            {
                float[] m = new float[16];
                for (int mi = 0; mi < 16; mi++)
                {
                    m[mi] = BinaryPrimitives.ReadSingleBigEndian(span.Slice((int)ptrMatrices + mi * 4, 4));
                }
                entry.TransformMatrix = m;
            }

            rcb.Entries.Add(entry);
        }

        // Relocation table
        if (payloadSize > 0 && payloadSize < (uint)data.Length)
        {
            for (int r = (int)payloadSize; r + 4 <= data.Length; r += 4)
            {
                uint rel = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(r, 4));
                if (rel > 0) rcb.Relocations.Add(rel);
            }
        }

        return rcb;
    }

    public static TreeNodeModel ToTreeNode(RcbData rcb)
    {
        var root = new TreeNodeModel($"RCB Character/Rigid Body (Version 0x{rcb.Version:X2}, Asset 0x{rcb.AssetHash:08X}, {rcb.Entries.Count} Slices, {rcb.Relocations.Count} Relocs)");
        var children = new List<TreeNodeModel>();

        foreach (var entry in rcb.Entries)
        {
            var node = new TreeNodeModel($"[{entry.Index}] \"{entry.Name}\" (Hash=0x{entry.HashId:08X}, Bones={entry.BoneCount})");
            var sub = new List<TreeNodeModel>
            {
                new($"Bone / Collision Shape Count: {entry.BoneCount}"),
                new($"Transform Data Offset: 0x{entry.PtrTransform:X4}"),
                new($"Bounds Data Offset: 0x{entry.PtrBounds:X4}")
            };

            if (entry.TransformMatrix != null)
            {
                var m = entry.TransformMatrix;
                var matNode = new TreeNodeModel($"4x4 Matrix at 0x{entry.PtrMatrices:X4}", new List<TreeNodeModel>
                {
                    new($"R0: [{m[0]:F4}, {m[1]:F4}, {m[2]:F4}, {m[3]:F4}]"),
                    new($"R1: [{m[4]:F4}, {m[5]:F4}, {m[6]:F4}, {m[7]:F4}]"),
                    new($"R2: [{m[8]:F4}, {m[9]:F4}, {m[10]:F4}, {m[11]:F4}]"),
                    new($"R3: [{m[12]:F4}, {m[13]:F4}, {m[14]:F4}, {m[15]:F4}] (Translation)")
                });
                sub.Add(matNode);
            }

            node.Children = sub;
            children.Add(node);
        }

        if (rcb.Relocations.Count > 0)
        {
            children.Add(new TreeNodeModel($"Pointer Relocations ({rcb.Relocations.Count} offsets)",
                rcb.Relocations.Take(50).Select((r, i) => new TreeNodeModel($"[{i}] Fixup at 0x{r:04X}")).ToList()));
        }

        root.Children = children;
        return root;
    }

    public static TableDataModel ToTable(RcbData rcb)
    {
        var model = new TableDataModel
        {
            Headers = new List<string> { "Index", "Name", "HashID", "BoneCount", "PtrTransform", "PtrMatrices", "PtrBounds" },
            Summary = $"RCB: {rcb.Entries.Count} component slices, Asset 0x{rcb.AssetHash:08X}, {rcb.Relocations.Count} pointer relocations"
        };

        foreach (var entry in rcb.Entries)
        {
            model.Rows.Add(new List<string>
            {
                entry.Index.ToString(),
                string.IsNullOrEmpty(entry.Name) ? "(unnamed)" : entry.Name,
                $"0x{entry.HashId:08X}",
                entry.BoneCount.ToString(),
                $"0x{entry.PtrTransform:04X}",
                $"0x{entry.PtrMatrices:04X}",
                $"0x{entry.PtrBounds:04X}"
            });
        }

        return model;
    }
}

