using System.Buffers.Binary;
using System.Text;

namespace TheSimpsonsGame.FileViewer.Formats;

public static class TxdParser
{
    private static readonly byte[] Ps3NativeMarker = new byte[] { 0x2D, 0x00, 0x02, 0x1C, 0x00, 0x00, 0x00, 0x0A };

    public static bool IsTxd(byte[] payload, string fileName = "", string resourceType = "")
    {
        if (resourceType.Equals("RWID_TEXDICTIONARY", StringComparison.OrdinalIgnoreCase)) return true;
        if (fileName.EndsWith(".txd", StringComparison.OrdinalIgnoreCase)) return true;
        if (payload.Length >= 4 && BinaryPrimitives.ReadUInt32LittleEndian(payload.AsSpan(0, 4)) == 0x16) return true;
        return false;
    }

    public static List<TextureImageInfo> ParseTextures(byte[] payload)
    {
        var textures = new List<TextureImageInfo>();
        if (payload.Length < 24) return textures;

        ReadOnlySpan<byte> span = payload;
        uint rootChunk = BinaryPrimitives.ReadUInt32LittleEndian(span.Slice(0, 4));
        if (rootChunk != 0x16) // rwID_TEXDICTIONARY
            return textures;

        for (int i = 0; i <= payload.Length - 0x64; i++)
        {
            if (span.Slice(i, Ps3NativeMarker.Length).SequenceEqual(Ps3NativeMarker))
            {
                int markerPos = i;
                int namePos = markerPos + 12;

                int nameLen = 0;
                while (namePos + nameLen < payload.Length && payload[namePos + nameLen] != 0 && nameLen < 32)
                    nameLen++;

                string name = Encoding.ASCII.GetString(payload, namePos, nameLen);

                int metaPos = markerPos + 44;
                if (metaPos + 16 > payload.Length) continue;

                byte formatCode = payload[metaPos];
                byte mipCount = payload[metaPos + 1];
                ushort width = BinaryPrimitives.ReadUInt16BigEndian(span.Slice(metaPos + 4, 2));
                ushort height = BinaryPrimitives.ReadUInt16BigEndian(span.Slice(metaPos + 6, 2));

                if (width == 0 || height == 0 || width > 4096 || height > 4096)
                {
                    // Fallback to little-endian if BE produced zeroes
                    width = BinaryPrimitives.ReadUInt16LittleEndian(span.Slice(metaPos + 4, 2));
                    height = BinaryPrimitives.ReadUInt16LittleEndian(span.Slice(metaPos + 6, 2));
                }

                int dataPos = markerPos + 76;
                int dataSize = CalculateDataSize(width, height, formatCode);

                if (dataPos + dataSize <= payload.Length && width > 0 && height > 0)
                {
                    byte[] rawData = payload[dataPos..(dataPos + dataSize)];
                    byte[] rgba = DecodeToRgba(rawData, width, height, formatCode);
                    byte[] dds = CreateDds(rawData, width, height, formatCode, mipCount);

                    textures.Add(new TextureImageInfo
                    {
                        Name = string.IsNullOrWhiteSpace(name) ? $"Texture_{textures.Count}" : name,
                        Width = width,
                        Height = height,
                        FormatCode = formatCode,
                        FormatName = GetFormatName(formatCode),
                        MipCount = Math.Max((int)mipCount, 1),
                        RgbaPixels = rgba,
                        DdsBytes = dds
                    });

                    i = dataPos + dataSize - 1;
                }
            }
        }

        return textures;
    }

    public static string GetFormatName(byte code) => code switch
    {
        0x86 => "DXT1",
        0x87 => "DXT3",
        0x88 => "DXT5",
        0x85 or 0xA5 => "ARGB8888",
        0x82 => "RGB565",
        _ => $"0x{code:X2}"
    };

    private static int CalculateDataSize(int width, int height, byte format)
    {
        return format switch
        {
            0x86 => Math.Max(1, (width + 3) / 4) * Math.Max(1, (height + 3) / 4) * 8, // DXT1
            0x87 or 0x88 => Math.Max(1, (width + 3) / 4) * Math.Max(1, (height + 3) / 4) * 16, // DXT3 / DXT5
            0x85 or 0xA5 => width * height * 4, // ARGB8888
            0x82 => width * height * 2, // RGB565
            _ => width * height * 4
        };
    }

    public static int MortonEncode2D(int x, int y)
    {
        x = (x | (x << 8)) & 0x00FF00FF;
        x = (x | (x << 4)) & 0x0F0F0F0F;
        x = (x | (x << 2)) & 0x33333333;
        x = (x | (x << 1)) & 0x55555555;

        y = (y | (y << 8)) & 0x00FF00FF;
        y = (y | (y << 4)) & 0x0F0F0F0F;
        y = (y | (y << 2)) & 0x33333333;
        y = (y | (y << 1)) & 0x55555555;
        return x | (y << 1);
    }

    public static byte[] Unswizzle(byte[] swizzled, int width, int height, int bpp)
    {
        int size = width * height * bpp;
        if (swizzled.Length < size) return swizzled;

        byte[] linear = new byte[size];
        for (int y = 0; y < height; y++)
        {
            for (int x = 0; x < width; x++)
            {
                int morton = MortonEncode2D(x, y);
                int src = morton * bpp;
                int dst = (y * width + x) * bpp;
                if (src + bpp <= swizzled.Length && dst + bpp <= linear.Length)
                {
                    Array.Copy(swizzled, src, linear, dst, bpp);
                }
            }
        }
        return linear;
    }

    public static byte[] DecodeToRgba(byte[] data, int width, int height, byte format)
    {
        byte[] rgba = new byte[width * height * 4];

        try
        {
            switch (format)
            {
                case 0x86: // DXT1
                    DecodeDxt1(data, width, height, rgba);
                    break;
                case 0x87: // DXT3
                    DecodeDxt3(data, width, height, rgba);
                    break;
                case 0x88: // DXT5
                    DecodeDxt5(data, width, height, rgba);
                    break;
                case 0x85 or 0xA5: // ARGB8888 (Morton swizzled or linear)
                    byte[] linear = Unswizzle(data, width, height, 4);
                    for (int i = 0; i < width * height; i++)
                    {
                        int idx = i * 4;
                        byte a = linear[idx];
                        byte r = linear[idx + 1];
                        byte g = linear[idx + 2];
                        byte b = linear[idx + 3];
                        rgba[idx] = r;
                        rgba[idx + 1] = g;
                        rgba[idx + 2] = b;
                        rgba[idx + 3] = a;
                    }
                    break;
                case 0x82: // RGB565
                    byte[] linear565 = Unswizzle(data, width, height, 2);
                    for (int i = 0; i < width * height; i++)
                    {
                        int srcIdx = i * 2;
                        int dstIdx = i * 4;
                        ushort val = BinaryPrimitives.ReadUInt16BigEndian(linear565.AsSpan(srcIdx, 2));
                        rgba[dstIdx] = (byte)(((val >> 11) & 0x1F) * 255 / 31);
                        rgba[dstIdx + 1] = (byte)(((val >> 5) & 0x3F) * 255 / 63);
                        rgba[dstIdx + 2] = (byte)((val & 0x1F) * 255 / 31);
                        rgba[dstIdx + 3] = 255;
                    }
                    break;
                default:
                    // Fill with opaque gray for unsupported
                    Array.Fill<byte>(rgba, 128);
                    break;
            }
        }
        catch
        {
            // Safeguard against invalid texture bounds
        }

        return rgba;
    }

    private static void DecodeDxt1(byte[] data, int width, int height, byte[] rgba)
    {
        int blocksX = (width + 3) / 4;
        int blocksY = (height + 3) / 4;
        int offset = 0;

        for (int by = 0; by < blocksY; by++)
        {
            for (int bx = 0; bx < blocksX; bx++)
            {
                if (offset + 8 > data.Length) return;

                ushort c0 = BinaryPrimitives.ReadUInt16LittleEndian(data.AsSpan(offset, 2));
                ushort c1 = BinaryPrimitives.ReadUInt16LittleEndian(data.AsSpan(offset + 2, 2));
                uint table = BinaryPrimitives.ReadUInt32LittleEndian(data.AsSpan(offset + 4, 4));
                offset += 8;

                RgbColor[] colors = new RgbColor[4];
                colors[0] = Rgb565ToRgb(c0);
                colors[1] = Rgb565ToRgb(c1);

                if (c0 > c1)
                {
                    colors[2] = new RgbColor((byte)((2 * colors[0].R + colors[1].R) / 3), (byte)((2 * colors[0].G + colors[1].G) / 3), (byte)((2 * colors[0].B + colors[1].B) / 3), 255);
                    colors[3] = new RgbColor((byte)((colors[0].R + 2 * colors[1].R) / 3), (byte)((colors[0].G + 2 * colors[1].G) / 3), (byte)((colors[0].B + 2 * colors[1].B) / 3), 255);
                }
                else
                {
                    colors[2] = new RgbColor((byte)((colors[0].R + colors[1].R) / 2), (byte)((colors[0].G + colors[1].G) / 2), (byte)((colors[0].B + colors[1].B) / 2), 255);
                    colors[3] = new RgbColor(0, 0, 0, 0);
                }

                for (int py = 0; py < 4; py++)
                {
                    for (int px = 0; px < 4; px++)
                    {
                        int x = bx * 4 + px;
                        int y = by * 4 + py;
                        if (x < width && y < height)
                        {
                            int code = (int)((table >> (2 * (py * 4 + px))) & 0x03);
                            var col = colors[code];
                            int dst = (y * width + x) * 4;
                            rgba[dst] = col.R;
                            rgba[dst + 1] = col.G;
                            rgba[dst + 2] = col.B;
                            rgba[dst + 3] = col.A;
                        }
                    }
                }
            }
        }
    }

    private static void DecodeDxt3(byte[] data, int width, int height, byte[] rgba)
    {
        int blocksX = (width + 3) / 4;
        int blocksY = (height + 3) / 4;
        int offset = 0;

        for (int by = 0; by < blocksY; by++)
        {
            for (int bx = 0; bx < blocksX; bx++)
            {
                if (offset + 16 > data.Length) return;

                ulong alphaBits = BinaryPrimitives.ReadUInt64LittleEndian(data.AsSpan(offset, 8));
                ushort c0 = BinaryPrimitives.ReadUInt16LittleEndian(data.AsSpan(offset + 8, 2));
                ushort c1 = BinaryPrimitives.ReadUInt16LittleEndian(data.AsSpan(offset + 10, 2));
                uint table = BinaryPrimitives.ReadUInt32LittleEndian(data.AsSpan(offset + 12, 4));
                offset += 16;

                RgbColor[] colors = new RgbColor[4];
                colors[0] = Rgb565ToRgb(c0);
                colors[1] = Rgb565ToRgb(c1);
                colors[2] = new RgbColor((byte)((2 * colors[0].R + colors[1].R) / 3), (byte)((2 * colors[0].G + colors[1].G) / 3), (byte)((2 * colors[0].B + colors[1].B) / 3), 255);
                colors[3] = new RgbColor((byte)((colors[0].R + 2 * colors[1].R) / 3), (byte)((colors[0].G + 2 * colors[1].G) / 3), (byte)((colors[0].B + 2 * colors[1].B) / 3), 255);

                for (int py = 0; py < 4; py++)
                {
                    for (int px = 0; px < 4; px++)
                    {
                        int x = bx * 4 + px;
                        int y = by * 4 + py;
                        if (x < width && y < height)
                        {
                            int shift = (py * 4 + px) * 4;
                            byte a = (byte)(((alphaBits >> shift) & 0x0F) * 17);
                            int code = (int)((table >> (2 * (py * 4 + px))) & 0x03);
                            var col = colors[code];
                            int dst = (y * width + x) * 4;
                            rgba[dst] = col.R;
                            rgba[dst + 1] = col.G;
                            rgba[dst + 2] = col.B;
                            rgba[dst + 3] = a;
                        }
                    }
                }
            }
        }
    }

    private static void DecodeDxt5(byte[] data, int width, int height, byte[] rgba)
    {
        int blocksX = (width + 3) / 4;
        int blocksY = (height + 3) / 4;
        int offset = 0;

        for (int by = 0; by < blocksY; by++)
        {
            for (int bx = 0; bx < blocksX; bx++)
            {
                if (offset + 16 > data.Length) return;

                byte a0 = data[offset];
                byte a1 = data[offset + 1];
                ulong aBits = 0;
                for (int i = 0; i < 6; i++)
                    aBits |= (ulong)data[offset + 2 + i] << (i * 8);

                ushort c0 = BinaryPrimitives.ReadUInt16LittleEndian(data.AsSpan(offset + 8, 2));
                ushort c1 = BinaryPrimitives.ReadUInt16LittleEndian(data.AsSpan(offset + 10, 2));
                uint table = BinaryPrimitives.ReadUInt32LittleEndian(data.AsSpan(offset + 12, 4));
                offset += 16;

                byte[] alphas = new byte[8];
                alphas[0] = a0;
                alphas[1] = a1;
                if (a0 > a1)
                {
                    for (int i = 1; i <= 6; i++)
                        alphas[i + 1] = (byte)(((7 - i) * a0 + i * a1) / 7);
                }
                else
                {
                    for (int i = 1; i <= 4; i++)
                        alphas[i + 1] = (byte)(((5 - i) * a0 + i * a1) / 5);
                    alphas[6] = 0;
                    alphas[7] = 255;
                }

                RgbColor[] colors = new RgbColor[4];
                colors[0] = Rgb565ToRgb(c0);
                colors[1] = Rgb565ToRgb(c1);
                colors[2] = new RgbColor((byte)((2 * colors[0].R + colors[1].R) / 3), (byte)((2 * colors[0].G + colors[1].G) / 3), (byte)((2 * colors[0].B + colors[1].B) / 3), 255);
                colors[3] = new RgbColor((byte)((colors[0].R + 2 * colors[1].R) / 3), (byte)((colors[0].G + 2 * colors[1].G) / 3), (byte)((colors[0].B + 2 * colors[1].B) / 3), 255);

                for (int py = 0; py < 4; py++)
                {
                    for (int px = 0; px < 4; px++)
                    {
                        int x = bx * 4 + px;
                        int y = by * 4 + py;
                        if (x < width && y < height)
                        {
                            int aCode = (int)((aBits >> (3 * (py * 4 + px))) & 0x07);
                            int cCode = (int)((table >> (2 * (py * 4 + px))) & 0x03);
                            var col = colors[cCode];
                            int dst = (y * width + x) * 4;
                            rgba[dst] = col.R;
                            rgba[dst + 1] = col.G;
                            rgba[dst + 2] = col.B;
                            rgba[dst + 3] = alphas[aCode];
                        }
                    }
                }
            }
        }
    }

    private readonly record struct RgbColor(byte R, byte G, byte B, byte A);

    private static RgbColor Rgb565ToRgb(ushort val)
    {
        byte r = (byte)(((val >> 11) & 0x1F) * 255 / 31);
        byte g = (byte)(((val >> 5) & 0x3F) * 255 / 63);
        byte b = (byte)((val & 0x1F) * 255 / 31);
        return new RgbColor(r, g, b, 255);
    }

    public static byte[] CreateDds(byte[] rawData, int width, int height, byte format, byte mipCount)
    {
        byte[] dds = new byte[128 + rawData.Length];
        Encoding.ASCII.GetBytes("DDS ").CopyTo(dds, 0);
        BinaryPrimitives.WriteInt32LittleEndian(dds.AsSpan(4, 4), 124); // header size
        BinaryPrimitives.WriteInt32LittleEndian(dds.AsSpan(8, 4), 0x00081007); // flags
        BinaryPrimitives.WriteInt32LittleEndian(dds.AsSpan(12, 4), height);
        BinaryPrimitives.WriteInt32LittleEndian(dds.AsSpan(16, 4), width);
        BinaryPrimitives.WriteInt32LittleEndian(dds.AsSpan(28, 4), Math.Max((int)mipCount, 1));

        // Pixel format at +76
        BinaryPrimitives.WriteInt32LittleEndian(dds.AsSpan(76, 4), 32); // size
        if (format == 0x86)
        {
            BinaryPrimitives.WriteInt32LittleEndian(dds.AsSpan(80, 4), 4); // DDPF_FOURCC
            Encoding.ASCII.GetBytes("DXT1").CopyTo(dds, 84);
        }
        else if (format == 0x87)
        {
            BinaryPrimitives.WriteInt32LittleEndian(dds.AsSpan(80, 4), 4);
            Encoding.ASCII.GetBytes("DXT3").CopyTo(dds, 84);
        }
        else if (format == 0x88)
        {
            BinaryPrimitives.WriteInt32LittleEndian(dds.AsSpan(80, 4), 4);
            Encoding.ASCII.GetBytes("DXT5").CopyTo(dds, 84);
        }
        else
        {
            BinaryPrimitives.WriteInt32LittleEndian(dds.AsSpan(80, 4), 0x41); // DDPF_RGB | DDPF_ALPHAPIXELS
            BinaryPrimitives.WriteInt32LittleEndian(dds.AsSpan(88, 4), 32); // RGBBitCount
            BinaryPrimitives.WriteUInt32LittleEndian(dds.AsSpan(92, 4), 0x00FF0000); // R
            BinaryPrimitives.WriteUInt32LittleEndian(dds.AsSpan(96, 4), 0x0000FF00); // G
            BinaryPrimitives.WriteUInt32LittleEndian(dds.AsSpan(100, 4), 0x000000FF); // B
            BinaryPrimitives.WriteUInt32LittleEndian(dds.AsSpan(104, 4), 0xFF000000); // A
        }

        BinaryPrimitives.WriteInt32LittleEndian(dds.AsSpan(108, 4), 0x1000); // caps
        rawData.CopyTo(dds, 128);
        return dds;
    }
}

