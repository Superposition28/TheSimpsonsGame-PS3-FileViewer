using System.Buffers.Binary;

namespace TheSimpsonsGame.FileViewer.Formats;

public class SimEntityData
{
    public int Index { get; set; }
    public string Guid { get; set; } = string.Empty;
    public uint BehaviorId { get; set; }
    public byte SpawnMask { get; set; }
    public byte AttachedCount { get; set; }
    public byte AttributeCount { get; set; }
    public List<string> AttachedResourceGuids { get; } = new();
    public List<uint> AttributeHandlers { get; } = new();
}

public class SimGroupData
{
    public uint Version { get; set; }
    public uint Guid32 { get; set; }
    public uint Flags { get; set; }
    public uint EntityCount { get; set; }
    public List<SimEntityData> Entities { get; } = new();
}

public static class SimGroupParser
{
    public const uint Magic = 0x53696D47; // "SimG"

    public static SimGroupData? Parse(byte[] data)
    {
        if (data.Length < 0x30) return null;

        // Legacy SimGroup base correction (+4 shift)
        if (data.Length >= 8 && data.AsSpan(4, 4).SequenceEqual("SimG"u8))
        {
            byte[] corrected = new byte[data.Length + 4];
            data.CopyTo(corrected, 4);
            data = corrected;
        }

        ReadOnlySpan<byte> span = data;
        uint magic = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(8, 4));
        if (magic != Magic) return null;

        var simGroup = new SimGroupData
        {
            Version = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(0x0C, 4)),
            Guid32 = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(0x10, 4)),
            Flags = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(0x14, 4)),
            EntityCount = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(0x18, 4))
        };

        uint ppEntPackets = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(0x28, 4));
        uint pEntPackets = 0;
        if (ppEntPackets > 0 && ppEntPackets + 4 <= (uint)data.Length)
        {
            pEntPackets = BinaryPrimitives.ReadUInt32BigEndian(span.Slice((int)ppEntPackets, 4));
        }

        if (pEntPackets > 0 && pEntPackets < (uint)data.Length)
        {
            int packetPos = (int)pEntPackets;
            for (int i = 0; i < simGroup.EntityCount; i++)
            {
                if (packetPos + 0x20 > data.Length) break;

                byte spawnMask = span[packetPos + 0x11];
                byte nAttached = span[packetPos + 0x12];
                byte nAttrs = span[packetPos + 0x13];
                int guidRelOff = BinaryPrimitives.ReadInt32BigEndian(span.Slice(packetPos + 0x18, 4));
                uint behavior = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(packetPos + 0x1C, 4));

                string entityGuid = "";
                int guidAbs = packetPos + 0x18 + guidRelOff;
                if (guidAbs >= 0 && guidAbs + 16 <= data.Length)
                {
                    entityGuid = Convert.ToHexString(data.AsSpan(guidAbs, 16));
                }

                var entity = new SimEntityData
                {
                    Index = i,
                    Guid = entityGuid,
                    BehaviorId = behavior,
                    SpawnMask = spawnMask,
                    AttachedCount = nAttached,
                    AttributeCount = nAttrs
                };

                int tablePos = packetPos + 0x20;
                if (tablePos + 4 * (nAttached + nAttrs) <= data.Length)
                {
                    for (int a = 0; a < nAttached; a++)
                    {
                        int ptrPos = tablePos + (a * 4);
                        int rel = BinaryPrimitives.ReadInt32BigEndian(span.Slice(ptrPos, 4));
                        int target = ptrPos + rel;
                        if (target >= 0 && target + 16 <= data.Length)
                        {
                            entity.AttachedResourceGuids.Add(Convert.ToHexString(data.AsSpan(target, 16)));
                        }
                    }

                    for (int at = 0; at < nAttrs; at++)
                    {
                        int ptrPos = tablePos + (nAttached * 4) + (at * 4);
                        int rel = BinaryPrimitives.ReadInt32BigEndian(span.Slice(ptrPos, 4));
                        int target = ptrPos + rel;
                        if (target >= 0 && target + 4 <= data.Length)
                        {
                            uint handler = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(target, 4));
                            entity.AttributeHandlers.Add(handler);
                        }
                    }

                    packetPos = tablePos + 4 * (nAttached + nAttrs);
                }
                else
                {
                    packetPos += 0x20;
                }

                simGroup.Entities.Add(entity);
            }
        }

        return simGroup;
    }

    public static TreeNodeModel ToTreeNode(SimGroupData group)
    {
        var root = new TreeNodeModel($"SimGroup (Version {group.Version}, GUID {group.Guid32:08X}, {group.Entities.Count} Entities)");
        var list = new List<TreeNodeModel>();

        foreach (var ent in group.Entities)
        {
            var entNode = new TreeNodeModel($"Entity {ent.Index}: GUID={ent.Guid} (Behavior={ent.BehaviorId:08X})");
            var children = new List<TreeNodeModel>
            {
                new($"Spawn Mask: 0x{ent.SpawnMask:X2}"),
                new($"Attached Resources ({ent.AttachedResourceGuids.Count})",
                    ent.AttachedResourceGuids.Select(g => new TreeNodeModel($"GUID: {g}")).ToList()),
                new($"Attribute Handlers ({ent.AttributeHandlers.Count})",
                    ent.AttributeHandlers.Select(h => new TreeNodeModel($"Handler: 0x{h:08X}")).ToList())
            };
            entNode.Children = children;
            list.Add(entNode);
        }

        root.Children = list;
        return root;
    }
}

