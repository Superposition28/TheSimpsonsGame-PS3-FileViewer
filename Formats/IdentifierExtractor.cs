using System.Buffers.Binary;
using System.Text;

namespace TheSimpsonsGame.FileViewer.Formats;

public static class IdentifierExtractor
{
    private static readonly HashSet<string> InvalidGuids = new(StringComparer.OrdinalIgnoreCase)
    {
        new string('0', 32),
        new string('F', 32),
        "BADBADBABEEFBEEFEAC15A5591100911"
    };

    public static (List<IdentifierItem> Ids, string Status) Extract(byte[] data, string format)
    {
        var ids = new List<IdentifierItem>();
        if (data == null || data.Length == 0)
            return (ids, "empty payload");

        string kind = format.ToLowerInvariant();
        try
        {
            if (kind == ".lh2")
            {
                ExtractLh2(data, ids);
                return (ids, $"LH2: {ids.Count} StringIDs extracted");
            }
            if (kind == ".alb")
            {
                ExtractAlb(data, ids);
                return (ids, $"ALB: {ids.Count} audio/subtitle identifiers extracted");
            }
            if (kind == ".smb")
            {
                ExtractSmb(data, ids);
                return (ids, $"SMB: {ids.Count} stream identifiers extracted");
            }
            if (kind == ".dat.simgroup" || kind == ".simgroup.dat")
            {
                ExtractSimGroup(data, ids);
                return (ids, $"SimGroup: {ids.Count} entity/resource identifiers extracted");
            }
            if (kind == ".txd")
            {
                ExtractTxd(data, ids);
                return (ids, $"TXD: {ids.Count} texture definitions extracted");
            }
            if (kind == ".preinstanced")
            {
                ExtractPreinstanced(data, ids);
                return (ids, $"Preinstanced: {ids.Count} texture references extracted");
            }
            if (kind == ".cec.ps3" || kind == ".cec")
            {
                ExtractCec(data, ids);
                return (ids, $"CEC: {ids.Count} configuration IDs extracted");
            }
            if (kind == ".tox.ps3" || kind == ".tob")
            {
                ExtractTob(data, ids);
                return (ids, $"TOB: {ids.Count} subtitle StringIDs extracted");
            }
            if (kind == ".meta.xml")
            {
                ExtractMetaModel(data, ids);
                return (ids, $"MetaModel: {ids.Count} asset GUIDs extracted");
            }
        }
        catch (Exception ex)
        {
            return (ids, $"Error extracting identifiers: {ex.Message}");
        }

        return (ids, "no structural IDs extracted");
    }

    private static void ExtractLh2(byte[] data, List<IdentifierItem> ids)
    {
        if (data.Length < 0x20 || !data.AsSpan(0, 4).SequenceEqual("2HCL"u8)) return;
        ReadOnlySpan<byte> span = data;
        uint count = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(0x10, 4));
        int idArrayOffset = 0x20;

        for (int i = 0; i < count && idArrayOffset + (i * 4) + 4 <= data.Length; i++)
        {
            uint sid = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(idArrayOffset + (i * 4), 4));
            ids.Add(new IdentifierItem
            {
                Namespace = "string.id",
                Value = $"{sid:08X}",
                Role = "definition",
                Offset = idArrayOffset + (i * 4),
                Width = 4,
                Endian = "BE",
                Label = $"Row {i} StringID definition",
                Confidence = "structural",
                Doc = "PS3_GAME/FormatAnalysis/STR/imbedded-formats/lh2.html"
            });
        }
    }

    private static void ExtractAlb(byte[] data, List<IdentifierItem> ids)
    {
        if (data.Length < 8) return;
        ReadOnlySpan<byte> span = data;
        ushort count = BinaryPrimitives.ReadUInt16BigEndian(span.Slice(2, 2));
        int start = 8;

        for (int i = 0; i < count && start + (i * 24) + 24 <= data.Length; i++)
        {
            int offset = start + (i * 24);
            var rec = span.Slice(offset, 24);
            uint alias = BinaryPrimitives.ReadUInt32BigEndian(rec.Slice(0, 4));
            uint bank = BinaryPrimitives.ReadUInt32BigEndian(rec.Slice(4, 4));
            uint stream = BinaryPrimitives.ReadUInt32BigEndian(rec.Slice(8, 4));
            uint stringId = BinaryPrimitives.ReadUInt32BigEndian(rec.Slice(20, 4));

            ids.Add(new IdentifierItem
            {
                Namespace = "audio.alias",
                Value = $"{alias:08X}",
                Role = "definition",
                Offset = offset,
                Width = 4,
                Endian = "BE",
                Label = $"ALB entry {i} alias",
                Doc = "PS3_GAME/FormatAnalysis/STR/imbedded-formats/alb.html"
            });
            ids.Add(new IdentifierItem
            {
                Namespace = "audio.bank",
                Value = $"{bank:08X}",
                Role = "reference",
                Offset = offset + 4,
                Width = 4,
                Endian = "BE",
                Label = $"ALB entry {i} bank",
                Doc = "PS3_GAME/FormatAnalysis/STR/imbedded-formats/alb.html"
            });
            ids.Add(new IdentifierItem
            {
                Namespace = "audio.stream",
                Value = $"{stream:08X}",
                Role = "reference",
                Offset = offset + 8,
                Width = 4,
                Endian = "BE",
                Label = $"ALB entry {i} stream",
                Doc = "PS3_GAME/FormatAnalysis/STR/imbedded-formats/alb.html"
            });
            ids.Add(new IdentifierItem
            {
                Namespace = "string.id",
                Value = $"{stringId:08X}",
                Role = "reference",
                Offset = offset + 20,
                Width = 4,
                Endian = "BE",
                Label = $"ALB entry {i} subtitle StringID",
                Doc = "PS3_GAME/FormatAnalysis/STR/imbedded-formats/alb.html"
            });
        }
    }

    private static void ExtractSmb(byte[] data, List<IdentifierItem> ids)
    {
        if (data.Length < 24) return;
        ReadOnlySpan<byte> span = data;
        uint count = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(16, 4));
        uint table = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(20, 4));

        for (int i = 0; i < count && table + (i * 4) + 4 <= (uint)data.Length; i++)
        {
            uint offset = BinaryPrimitives.ReadUInt32BigEndian(span.Slice((int)table + (i * 4), 4));
            if (offset + 96 > (uint)data.Length) break;

            var rec = span.Slice((int)offset, 96);
            uint bank = BinaryPrimitives.ReadUInt32BigEndian(rec.Slice(4, 4));
            uint stream = BinaryPrimitives.ReadUInt32BigEndian(rec.Slice(8, 4));

            ids.Add(new IdentifierItem
            {
                Namespace = "audio.bank",
                Value = $"{bank:08X}",
                Role = "definition",
                Offset = (int)offset + 4,
                Width = 4,
                Endian = "BE",
                Label = $"SMB entry {i} bank",
                Doc = "PS3_GAME/FormatAnalysis/STR/imbedded-formats/smb.html"
            });
            ids.Add(new IdentifierItem
            {
                Namespace = "audio.stream",
                Value = $"{stream:08X}",
                Role = "definition",
                Offset = (int)offset + 8,
                Width = 4,
                Endian = "BE",
                Label = $"SMB entry {i} stream",
                Doc = "PS3_GAME/FormatAnalysis/STR/imbedded-formats/smb.html"
            });

            int nameStart = (int)offset + 52;
            int nullIdx = Array.IndexOf(data, (byte)0, nameStart, 96 - 52);
            int len = nullIdx >= 0 ? nullIdx - nameStart : (96 - 52);
            string name = Encoding.ASCII.GetString(data, nameStart, len);

            if (!string.IsNullOrWhiteSpace(name))
            {
                ids.Add(new IdentifierItem
                {
                    Namespace = "stream.filename",
                    Value = name.ToLowerInvariant(),
                    Role = "reference",
                    Offset = nameStart,
                    Width = len,
                    Endian = "ASCII",
                    Label = $"SMB entry {i} stream filename",
                    Doc = "PS3_GAME/FormatAnalysis/STR/imbedded-formats/smb.html"
                });
            }
        }
    }

    private static void ExtractSimGroup(byte[] data, List<IdentifierItem> ids)
    {
        var group = SimGroupParser.Parse(data);
        if (group == null) return;

        ids.Add(new IdentifierItem
        {
            Namespace = "simgroup.id",
            Value = $"{group.Guid32:08X}",
            Role = "definition",
            Offset = 16,
            Width = 4,
            Endian = "BE",
            Label = "SimGroup ID",
            Doc = "PS3_GAME/FormatAnalysis/STR/imbedded-formats/simgroup.dat.html#header"
        });

        foreach (var ent in group.Entities)
        {
            if (!string.IsNullOrEmpty(ent.Guid) && !InvalidGuids.Contains(ent.Guid))
            {
                ids.Add(new IdentifierItem
                {
                    Namespace = "entity.guid",
                    Value = ent.Guid,
                    Role = "definition",
                    Offset = 0,
                    Width = 16,
                    Endian = "BE words",
                    Label = $"Entity {ent.Index}",
                    Doc = "PS3_GAME/FormatAnalysis/STR/imbedded-formats/simgroup.dat.html#entity-entry"
                });
            }

            foreach (var resGuid in ent.AttachedResourceGuids)
            {
                if (!string.IsNullOrEmpty(resGuid) && !InvalidGuids.Contains(resGuid))
                {
                    ids.Add(new IdentifierItem
                    {
                        Namespace = "asset.guid",
                        Value = resGuid,
                        Role = "reference",
                        Offset = 0,
                        Width = 16,
                        Endian = "BE words",
                        Label = $"Entity {ent.Index} attached resource",
                        Doc = "PS3_GAME/FormatAnalysis/STR/imbedded-formats/simgroup.dat.html#entity-entry"
                    });
                }
            }
        }
    }

    private static void ExtractTxd(byte[] data, List<IdentifierItem> ids)
    {
        var textures = TxdParser.ParseTextures(data);
        foreach (var tex in textures)
        {
            if (!string.IsNullOrWhiteSpace(tex.Name))
            {
                ids.Add(new IdentifierItem
                {
                    Namespace = "texture.name",
                    Value = tex.Name.ToLowerInvariant(),
                    Role = "definition",
                    Offset = 0,
                    Width = tex.Name.Length,
                    Endian = "ASCII",
                    Label = $"TXD texture '{tex.Name}' ({tex.Width}x{tex.Height} {tex.FormatName})",
                    Doc = "PS3_GAME/FormatAnalysis/STR/imbedded-formats/txd.html"
                });
            }
        }
    }

    private static void ExtractPreinstanced(byte[] data, List<IdentifierItem> ids)
    {
        var mesh = PreinstancedParser.Parse(data);
        if (mesh == null) return;

        foreach (var tex in mesh.MaterialTextureNames)
        {
            ids.Add(new IdentifierItem
            {
                Namespace = "texture.name",
                Value = tex.ToLowerInvariant(),
                Role = "reference",
                Offset = 0,
                Width = tex.Length,
                Endian = "ASCII",
                Label = $"Preinstanced material texture '{tex}'",
                Doc = "PS3_GAME/FormatAnalysis/STR/imbedded-formats/preinstanced.html"
            });
        }
    }

    private static void ExtractCec(byte[] data, List<IdentifierItem> ids)
    {
        if (data.Length < 16) return;
        ReadOnlySpan<byte> span = data;
        ushort count = BinaryPrimitives.ReadUInt16BigEndian(span.Slice(6, 2));

        int pos = 16;
        for (int i = 0; i < count && pos + 8 <= data.Length; i++)
        {
            uint configId = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(pos, 4));
            ids.Add(new IdentifierItem
            {
                Namespace = "config.id",
                Value = $"{configId:08X}",
                Role = "definition",
                Offset = pos,
                Width = 4,
                Endian = "BE",
                Label = $"CEC config {i}",
                Doc = "PS3_GAME/FormatAnalysis/STR/imbedded-formats/cec.ps3.html"
            });
            pos += 8;
        }
    }

    private static void ExtractTob(byte[] data, List<IdentifierItem> ids)
    {
        if (data.Length < 16) return;
        ReadOnlySpan<byte> span = data;
        uint count = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(8, 4));

        int pos = 16;
        for (int i = 0; i < count && pos + 12 <= data.Length; i++)
        {
            uint sid = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(pos, 4));
            ids.Add(new IdentifierItem
            {
                Namespace = "string.id",
                Value = $"{sid:08X}",
                Role = "reference",
                Offset = pos,
                Width = 4,
                Endian = "BE",
                Label = $"TOB cue {i} StringID",
                Doc = "PS3_GAME/FormatAnalysis/STR/imbedded-formats/tox.PS3.html"
            });
            pos += 12;
        }
    }

    private static void ExtractMetaModel(byte[] data, List<IdentifierItem> ids)
    {
        if (data.Length < 24) return;
        ReadOnlySpan<byte> span = data;
        uint count = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(0, 4));

        int pos = 4;
        for (int i = 0; i < count && pos + 16 <= data.Length; i++)
        {
            string guid = Convert.ToHexString(data.AsSpan(pos, 16));
            if (!InvalidGuids.Contains(guid))
            {
                ids.Add(new IdentifierItem
                {
                    Namespace = "asset.guid",
                    Value = guid,
                    Role = "reference",
                    Offset = pos,
                    Width = 16,
                    Endian = "BE words",
                    Label = $"MetaModel asset {i} GUID",
                    Doc = "PS3_GAME/FormatAnalysis/STR/imbedded-formats/meta.xml.html"
                });
            }
            pos += 16;
        }
    }
}

