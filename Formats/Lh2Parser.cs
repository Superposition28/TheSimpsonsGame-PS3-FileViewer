using System.Buffers.Binary;
using System.Text;

namespace TheSimpsonsGame.FileViewer.Formats;

public static class Lh2Parser
{
    public const uint Magic = 0x3248434C; // "2HCL"

    public static TableDataModel ParseToTable(byte[] data)
    {
        var model = new TableDataModel();
        if (data.Length < 0x20)
        {
            model.Summary = "Data too small for LH2 header";
            return model;
        }

        ReadOnlySpan<byte> span = data;
        uint magic = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(0, 4));
        if (magic != Magic)
        {
            model.Summary = $"Invalid LH2 magic: 0x{magic:X8}";
            return model;
        }

        uint declaredSize = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(4, 4));
        uint entryCount = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(0x10, 4));
        uint tableCount = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(0x14, 4));

        int n = (int)entryCount;
        int t = (int)tableCount;

        int idArrayOffset = 0x20;
        int pointerMatrixOffset = idArrayOffset + (4 * n);
        int requiredSize = pointerMatrixOffset + (4 * n * t);

        if (requiredSize > data.Length)
        {
            model.Summary = "LH2 pointer matrix truncated";
            return model;
        }

        // Setup headers
        model.Headers.Add("StringID");
        if (t == 5)
        {
            model.Headers.AddRange(new[] { "EN", "FR", "IT", "ES", "Label" });
        }
        else
        {
            for (int col = 0; col < t; col++)
                model.Headers.Add($"Column {col}");
        }

        uint[] ids = new uint[n];
        for (int i = 0; i < n; i++)
        {
            ids[i] = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(idArrayOffset + (i * 4), 4));
        }

        for (int e = 0; e < n; e++)
        {
            var row = new List<string> { $"{ids[e]:08X}" };

            for (int col = 0; col < t; col++)
            {
                int colBase = pointerMatrixOffset + (col * n * 4);
                uint strOffset = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(colBase + (e * 4), 4));

                string text = "";
                if (strOffset < (uint)data.Length)
                {
                    int start = (int)strOffset;
                    int end = Array.IndexOf(data, (byte)0, start);
                    int len = end >= 0 ? end - start : data.Length - start;
                    text = Encoding.Latin1.GetString(data, start, len);
                }
                row.Add(text);
            }

            model.Rows.Add(row);
        }

        model.Summary = $"LH2: {n} rows, {t} columns; Windows-1252 source bytes";
        return model;
    }

    public static string ParseToCsv(byte[] data)
    {
        var table = ParseToTable(data);
        var sb = new StringBuilder();
        sb.AppendLine(string.Join(",", table.Headers));
        foreach (var row in table.Rows)
        {
            sb.AppendLine(string.Join(",", row.Select(c => $"\"{c.Replace("\"", "\"\"")}\"")));
        }
        return sb.ToString();
    }
}

