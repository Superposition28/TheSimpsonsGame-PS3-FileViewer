using System.Buffers.Binary;
using System.Text;

namespace TheSimpsonsGame.FileViewer.Formats;

public class PreinstancedSubmeshInfo
{
    public int Index { get; set; }
    public uint Flags { get; set; }
    public float BoundsRadius { get; set; }
    public uint MaterialId { get; set; }
    public string MaterialTextureName { get; set; } = string.Empty;
    public uint VertexStride { get; set; }
    public uint VertexCount { get; set; }
    public uint IndexCount { get; set; }
}

public class PreinstancedMeshData
{
    public string ObjectName { get; set; } = string.Empty;
    public uint FormatVersion { get; set; }
    public uint SubmeshCount { get; set; }
    public List<string> MaterialTextureNames { get; } = new();
    public List<PreinstancedSubmeshInfo> Submeshes { get; } = new();
}

public static class PreinstancedParser
{
    public static PreinstancedMeshData? Parse(byte[] payload, string objectName = "")
    {
        if (payload.Length < 12) return null;

        var mesh = new PreinstancedMeshData { ObjectName = objectName };
        ReadOnlySpan<byte> span = payload;

        // Scan RenderWare Clump chunks for material texture names and EA_EARS_MESH (0xEA33)
        int offset = 0;
        int earsMeshOffset = -1;
        int earsMeshSize = 0;

        while (offset + 12 <= payload.Length)
        {
            uint chunkId = BinaryPrimitives.ReadUInt32LittleEndian(span.Slice(offset, 4));
            uint chunkSize = BinaryPrimitives.ReadUInt32LittleEndian(span.Slice(offset + 4, 4));

            if (chunkId == 0x02 && chunkSize > 0 && chunkSize < 128) // rwID_STRING
            {
                int strStart = offset + 12;
                if (strStart + chunkSize <= payload.Length)
                {
                    int nullIdx = Array.IndexOf(payload, (byte)0, strStart, (int)chunkSize);
                    int len = nullIdx >= 0 ? nullIdx - strStart : (int)chunkSize;
                    string str = Encoding.ASCII.GetString(payload, strStart, len);
                    if (!string.IsNullOrWhiteSpace(str) && !mesh.MaterialTextureNames.Contains(str))
                    {
                        mesh.MaterialTextureNames.Add(str);
                    }
                }
            }

            if (chunkId == 0xEA33) // EA_EARS_MESH
            {
                earsMeshOffset = offset + 12;
                earsMeshSize = (int)chunkSize;
            }

            if (chunkSize == 0 || offset + 12 + chunkSize > payload.Length) break;
            offset += 12 + (int)chunkSize;
        }

        if (earsMeshOffset >= 0 && earsMeshOffset + 0x30 <= payload.Length)
        {
            ReadOnlySpan<byte> hSpan = span.Slice(earsMeshOffset);
            mesh.FormatVersion = BinaryPrimitives.ReadUInt32BigEndian(hSpan.Slice(0, 4));
            mesh.SubmeshCount = BinaryPrimitives.ReadUInt32BigEndian(hSpan.Slice(0x18, 4));

            uint submeshArrayOffset = BinaryPrimitives.ReadUInt32BigEndian(hSpan.Slice(0x20, 4));
            if (submeshArrayOffset > 0 && earsMeshOffset + submeshArrayOffset < payload.Length)
            {
                int submeshPos = earsMeshOffset + (int)submeshArrayOffset;
                for (int i = 0; i < mesh.SubmeshCount; i++)
                {
                    if (submeshPos + 0x50 > payload.Length) break;
                    var sSpan = span.Slice(submeshPos, 0x50);

                    uint flags = BinaryPrimitives.ReadUInt32BigEndian(sSpan.Slice(0, 4));
                    float radius = BinaryPrimitives.ReadSingleBigEndian(sSpan.Slice(4, 4));
                    uint matId = BinaryPrimitives.ReadUInt32BigEndian(sSpan.Slice(0x0C, 4));
                    uint vTotalSize = BinaryPrimitives.ReadUInt32BigEndian(sSpan.Slice(0x24, 4));
                    uint vStride = BinaryPrimitives.ReadUInt32BigEndian(sSpan.Slice(0x28, 4));
                    uint faceByteLen = BinaryPrimitives.ReadUInt32BigEndian(sSpan.Slice(0x44, 4));

                    string texName = (i < mesh.MaterialTextureNames.Count) ? mesh.MaterialTextureNames[i] : "";

                    mesh.Submeshes.Add(new PreinstancedSubmeshInfo
                    {
                        Index = i,
                        Flags = flags,
                        BoundsRadius = radius,
                        MaterialId = matId,
                        MaterialTextureName = texName,
                        VertexStride = vStride,
                        VertexCount = vStride > 0 ? vTotalSize / vStride : 0,
                        IndexCount = faceByteLen / 2
                    });

                    submeshPos += 0x50;
                }
            }
        }

        return mesh;
    }

    public static TreeNodeModel ToTreeNode(PreinstancedMeshData mesh)
    {
        var root = new TreeNodeModel($"Preinstanced Mesh (Version {mesh.FormatVersion}, {mesh.Submeshes.Count} Submeshes, {mesh.MaterialTextureNames.Count} Textures)");
        var children = new List<TreeNodeModel>();

        if (mesh.MaterialTextureNames.Count > 0)
        {
            children.Add(new TreeNodeModel($"Material Textures ({mesh.MaterialTextureNames.Count})",
                mesh.MaterialTextureNames.Select(t => new TreeNodeModel(t)).ToList()));
        }

        foreach (var sub in mesh.Submeshes)
        {
            children.Add(new TreeNodeModel(
                $"Submesh {sub.Index}: Vertices={sub.VertexCount} (Stride={sub.VertexStride}), Faces={sub.IndexCount / 3}, Radius={sub.BoundsRadius:F2}, Texture='{sub.MaterialTextureName}'"));
        }

        root.Children = children;
        return root;
    }
}

