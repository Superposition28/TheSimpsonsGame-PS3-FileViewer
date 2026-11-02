using System.Buffers.Binary;
using System.Text;

namespace TheSimpsonsGame.FileViewer.Formats;

public static class AudioLookups
{
    public static TableDataModel ParseAlbToTable(byte[] data)
    {
        var model = new TableDataModel
        {
            Headers = new List<string> { "Offset", "Alias", "Bank", "Stream", "StringID" }
        };

        if (data.Length < 8)
        {
            model.Summary = "Short ALB header";
            return model;
        }

        ReadOnlySpan<byte> span = data;
        ushort version = BinaryPrimitives.ReadUInt16BigEndian(span.Slice(0, 2));
        ushort count = BinaryPrimitives.ReadUInt16BigEndian(span.Slice(2, 2));
        uint start = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(4, 4));

        if (version != 6 || start != 8 || data.Length != start + (count * 24))
        {
            model.Summary = $"Unrecognized ALB layout: v{version}, count={count}, start={start}";
            return model;
        }

        for (int i = 0; i < count; i++)
        {
            int offset = (int)start + (i * 24);
            var rec = span.Slice(offset, 24);
            uint alias = BinaryPrimitives.ReadUInt32BigEndian(rec.Slice(0, 4));
            uint bank = BinaryPrimitives.ReadUInt32BigEndian(rec.Slice(4, 4));
            uint stream = BinaryPrimitives.ReadUInt32BigEndian(rec.Slice(8, 4));
            uint stringId = BinaryPrimitives.ReadUInt32BigEndian(rec.Slice(20, 4));

            model.Rows.Add(new List<string>
            {
                $"0x{offset:X4}",
                $"{alias:08X}",
                $"{bank:08X}",
                $"{stream:08X}",
                $"{stringId:08X}"
            });
        }

        model.Summary = $"ALB: {count} records (24 bytes each, version 6)";
        return model;
    }

    public static TableDataModel ParseSmbToTable(byte[] data)
    {
        var model = new TableDataModel
        {
            Headers = new List<string> { "Offset", "Bank", "Stream", "Filename" }
        };

        if (data.Length < 24)
        {
            model.Summary = "Short SMB header";
            return model;
        }

        ReadOnlySpan<byte> span = data;
        uint count = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(16, 4));
        uint table = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(20, 4));

        if (table != 24 || table + (count * 4) > (uint)data.Length)
        {
            model.Summary = "Invalid SMB pointer table";
            return model;
        }

        for (int i = 0; i < count; i++)
        {
            uint offset = BinaryPrimitives.ReadUInt32BigEndian(span.Slice((int)table + (i * 4), 4));
            if (offset + 96 > (uint)data.Length) break;

            var rec = span.Slice((int)offset, 96);
            uint bank = BinaryPrimitives.ReadUInt32BigEndian(rec.Slice(4, 4));
            uint stream = BinaryPrimitives.ReadUInt32BigEndian(rec.Slice(8, 4));

            int nameStart = (int)offset + 52;
            int nullIdx = Array.IndexOf(data, (byte)0, nameStart, 96 - 52);
            int len = nullIdx >= 0 ? nullIdx - nameStart : (96 - 52);
            string name = Encoding.ASCII.GetString(data, nameStart, len);

            model.Rows.Add(new List<string>
            {
                $"0x{offset:X4}",
                $"{bank:08X}",
                $"{stream:08X}",
                name
            });
        }

        model.Summary = $"SMB: {count} records (96 bytes each)";
        return model;
    }
}

