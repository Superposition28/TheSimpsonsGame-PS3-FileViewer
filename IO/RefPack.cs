using System.Buffers.Binary;

namespace TheSimpsonsGame.FileViewer.IO;

/// <summary>
/// EA RefPack (QuickBMS dk2 / QFS) decompressor used in RenderWare and EA stream containers.
/// Reimplemented exactly from reversing/docs/PS3_GAME/FormatAnalysis/STR/index.html.
/// </summary>
public static class RefPack
{
    public const ushort RefPackSignature = 0x10FB;

    public static bool IsRefPack(ReadOnlySpan<byte> data)
    {
        if (data.Length < 2) return false;
        ushort sig = (ushort)((data[0] << 8) | data[1]);
        return sig == 0x10FB || sig == 0x11FB;
    }

    public static byte[] Decompress(ReadOnlySpan<byte> data, int expectedSize = -1)
    {
        if (data.Length < 5)
            throw new InvalidDataException("RefPack stream too short for header");

        int inPos = 0;
        ushort sig = (ushort)((data[inPos++] << 8) | data[inPos++]);
        if (sig != 0x10FB && sig != 0x11FB)
            throw new InvalidDataException($"Invalid RefPack signature: 0x{sig:X4}");

        // If bit 0x0100 is set (e.g. 0x11FB), an optional 3-byte compressed size follows
        if ((sig & 0x0100) != 0)
        {
            inPos += 3;
        }

        // 3 bytes decompressed size (big-endian UInt24)
        int decompressedSize = (data[inPos++] << 16) | (data[inPos++] << 8) | data[inPos++];
        if (expectedSize > 0 && decompressedSize != expectedSize)
        {
            decompressedSize = expectedSize;
        }

        byte[] output = new byte[decompressedSize];
        int outPos = 0;

        while (inPos < data.Length && outPos < decompressedSize)
        {
            byte b0 = data[inPos++];

            if ((b0 & 0x80) == 0) // 2-byte command
            {
                if (inPos >= data.Length) break;
                byte b1 = data[inPos++];

                int literalCount = b0 & 0x03;
                for (int i = 0; i < literalCount && inPos < data.Length && outPos < decompressedSize; i++)
                    output[outPos++] = data[inPos++];

                int matchLength = ((b0 >> 2) & 0x07) + 3;
                int matchDistance = ((b0 & 0x60) << 3) + b1 + 1;
                int matchSrc = outPos - matchDistance;

                for (int i = 0; i < matchLength && outPos < decompressedSize; i++)
                    output[outPos++] = output[matchSrc + i];
            }
            else if ((b0 & 0xC0) == 0x80) // 3-byte command
            {
                if (inPos + 1 >= data.Length) break;
                byte b1 = data[inPos++];
                byte b2 = data[inPos++];

                int literalCount = b1 >> 6;
                for (int i = 0; i < literalCount && inPos < data.Length && outPos < decompressedSize; i++)
                    output[outPos++] = data[inPos++];

                int matchLength = (b0 & 0x3F) + 4;
                int matchDistance = ((b1 & 0x3F) << 8) + b2 + 1;
                int matchSrc = outPos - matchDistance;

                for (int i = 0; i < matchLength && outPos < decompressedSize; i++)
                    output[outPos++] = output[matchSrc + i];
            }
            else if ((b0 & 0xE0) == 0xC0) // 4-byte command
            {
                if (inPos + 2 >= data.Length) break;
                byte b1 = data[inPos++];
                byte b2 = data[inPos++];
                byte b3 = data[inPos++];

                int literalCount = b0 & 0x03;
                for (int i = 0; i < literalCount && inPos < data.Length && outPos < decompressedSize; i++)
                    output[outPos++] = data[inPos++];

                int matchLength = ((b0 & 0x0C) << 6) + b3 + 5;
                int matchDistance = ((b0 & 0x10) << 12) + (b1 << 8) + b2 + 1;
                int matchSrc = outPos - matchDistance;

                for (int i = 0; i < matchLength && outPos < decompressedSize; i++)
                    output[outPos++] = output[matchSrc + i];
            }
            else // 1-byte command (literal or stop)
            {
                int literalCount = (b0 & 0x1F) * 4 + 4;
                if (literalCount > 112)
                {
                    // 0xFC..0xFF are end markers with 0..3 trailing literal bytes
                    literalCount = b0 & 0x03;
                    for (int i = 0; i < literalCount && inPos < data.Length && outPos < decompressedSize; i++)
                        output[outPos++] = data[inPos++];
                    break;
                }

                for (int i = 0; i < literalCount && inPos < data.Length && outPos < decompressedSize; i++)
                    output[outPos++] = data[inPos++];
            }
        }

        return output;
    }
}

