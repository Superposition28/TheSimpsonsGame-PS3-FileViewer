using System.Text;

namespace TheSimpsonsGame.FileViewer.IO;

public static class HexDump
{
    public const int DefaultPageSize = 2048;

    public static string Format(ReadOnlySpan<byte> data, int baseOffset = 0)
    {
        var sb = new StringBuilder();
        int length = data.Length;

        for (int i = 0; i < length; i += 16)
        {
            int currentOffset = baseOffset + i;
            sb.Append($"{currentOffset:X8}  ");

            int chunkSize = Math.Min(16, length - i);

            // Hex values
            for (int j = 0; j < 16; j++)
            {
                if (j == 8) sb.Append(' ');
                if (j < chunkSize)
                {
                    sb.Append($"{data[i + j]:X2} ");
                }
                else
                {
                    sb.Append("   ");
                }
            }

            sb.Append(" |");

            // ASCII values
            for (int j = 0; j < chunkSize; j++)
            {
                byte b = data[i + j];
                char c = (b >= 32 && b <= 126) ? (char)b : '.';
                sb.Append(c);
            }

            sb.Append('|');
            sb.AppendLine();
        }

        return sb.ToString();
    }

    public static string FormatPage(byte[] data, int pageOffset, int pageSize = DefaultPageSize)
    {
        if (data == null || data.Length == 0) return "(empty data)";
        if (pageOffset < 0) pageOffset = 0;
        if (pageOffset >= data.Length) pageOffset = Math.Max(0, data.Length - pageSize);

        int count = Math.Min(pageSize, data.Length - pageOffset);
        return Format(data.AsSpan(pageOffset, count), pageOffset);
    }
}

