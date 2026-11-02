using System.Buffers.Binary;
using System.Text;

namespace TheSimpsonsGame.FileViewer.IO;

public record StrSectionDescriptor(
    uint MemoryPolicy,
    uint CompressorId,
    int DataSize,
    int AllocSize,
    int ReadSize,
    int ReadOffset,
    int FileOffset,
    bool IsCompressed);

public class StrChunk
{
    public ushort ChunkType { get; set; }
    public string TypeName { get; set; } = string.Empty;
    public int StartOffset { get; set; }
    public int PayloadStart { get; set; }
    public int PayloadSize { get; set; }
    public byte[] Data { get; set; } = Array.Empty<byte>();

    // Embedded asset fields
    public string FileName { get; set; } = string.Empty;
    public string ResourceType { get; set; } = string.Empty;
    public string FullPath { get; set; } = string.Empty;
    public string ExtraString { get; set; } = string.Empty;
    public string AssetGuid { get; set; } = string.Empty;
    public byte[] PayloadData { get; set; } = Array.Empty<byte>();
    public int HeaderSize { get; set; }
}

public class StrSection
{
    public int SectionIndex { get; set; }
    public StrSectionDescriptor Descriptor { get; set; } = null!;
    public List<StrChunk> Chunks { get; } = new();
}

public class StrStreamInfo
{
    public uint Guid { get; set; }
    public string FileName { get; set; } = string.Empty;
    public byte ParentsCount { get; set; }
    public byte ForceLoadCount { get; set; }
    public byte SectionCount { get; set; }
    public byte Flags { get; set; }
    public uint RelativesOffset { get; set; }
    public uint SectionInfoOffset { get; set; }
}

public class StrArchive
{
    public const uint Magic = 0x53546F63; // "SToc"

    public string FilePath { get; }
    public uint Version { get; private set; }
    public byte SectionCount { get; private set; }
    public byte PlatformId { get; private set; }
    public int StreamFileOffset { get; private set; }
    public int SectionArrayOffset { get; private set; }
    public StrStreamInfo? StreamInfo { get; private set; }

    public List<StrSection> Sections { get; } = new();

    public StrArchive(string filePath)
    {
        FilePath = filePath;
    }

    public static StrArchive Load(string filePath)
    {
        var archive = new StrArchive(filePath);
        archive.Read();
        return archive;
    }

    public static StrArchive Load(byte[] fileBytes, string filePath = "")
    {
        var archive = new StrArchive(filePath);
        archive.ReadFromBytes(fileBytes);
        return archive;
    }

    private void Read()
    {
        byte[] fileBytes = File.ReadAllBytes(FilePath);
        ReadFromBytes(fileBytes);
    }

    private void ReadFromBytes(byte[] fileBytes)
    {
        if (fileBytes.Length < 20)
            throw new InvalidDataException("STR file too small for SToc header");

        uint magic = BinaryPrimitives.ReadUInt32BigEndian(fileBytes.AsSpan(0, 4));
        if (magic != Magic)
            throw new InvalidDataException($"Invalid STR magic: 0x{magic:X8} (expected 'SToc')");

        Version = BinaryPrimitives.ReadUInt32BigEndian(fileBytes.AsSpan(4, 4));
        SectionCount = fileBytes[8];
        PlatformId = fileBytes[9];
        StreamFileOffset = BinaryPrimitives.ReadInt32BigEndian(fileBytes.AsSpan(12, 4));
        SectionArrayOffset = BinaryPrimitives.ReadInt32BigEndian(fileBytes.AsSpan(16, 4));

        if (StreamFileOffset > 0 && StreamFileOffset + 24 <= fileBytes.Length)
        {
            int nameRel = BinaryPrimitives.ReadInt32BigEndian(fileBytes.AsSpan(StreamFileOffset + 4, 4));
            int namePos = StreamFileOffset + nameRel;
            string streamFileName = "";
            if (namePos >= 0 && namePos < fileBytes.Length)
            {
                int end = Array.IndexOf(fileBytes, (byte)0, namePos);
                int len = end >= 0 ? end - namePos : fileBytes.Length - namePos;
                streamFileName = Encoding.ASCII.GetString(fileBytes, namePos, len);
            }

            StreamInfo = new StrStreamInfo
            {
                Guid = BinaryPrimitives.ReadUInt32BigEndian(fileBytes.AsSpan(StreamFileOffset, 4)),
                FileName = streamFileName,
                ParentsCount = fileBytes[StreamFileOffset + 8],
                ForceLoadCount = fileBytes[StreamFileOffset + 9],
                SectionCount = fileBytes[StreamFileOffset + 10],
                Flags = fileBytes[StreamFileOffset + 11],
                RelativesOffset = BinaryPrimitives.ReadUInt32BigEndian(fileBytes.AsSpan(StreamFileOffset + 16, 4)),
                SectionInfoOffset = BinaryPrimitives.ReadUInt32BigEndian(fileBytes.AsSpan(StreamFileOffset + 20, 4))
            };
        }

        int dataBase = (SectionArrayOffset + (SectionCount * 24) + 0x7FF) & ~0x7FF;
        int descriptorPos = SectionArrayOffset;
        int currentDataPos = dataBase;

        for (int i = 0; i < SectionCount; i++)
        {
            if (descriptorPos + 24 > fileBytes.Length) break;
            var span = fileBytes.AsSpan(descriptorPos, 24);
            int dataSize = BinaryPrimitives.ReadInt32BigEndian(span[8..12]);
            int readSize = BinaryPrimitives.ReadInt32BigEndian(span[16..20]);

            if (currentDataPos + readSize > fileBytes.Length)
                break;

            ReadOnlySpan<byte> packedSpan = fileBytes.AsSpan(currentDataPos, readSize);
            bool isCompressed = RefPack.IsRefPack(packedSpan);

            var desc = new StrSectionDescriptor(
                MemoryPolicy: BinaryPrimitives.ReadUInt32BigEndian(span[0..4]),
                CompressorId: BinaryPrimitives.ReadUInt32BigEndian(span[4..8]),
                DataSize: dataSize,
                AllocSize: BinaryPrimitives.ReadInt32BigEndian(span[12..16]),
                ReadSize: readSize,
                ReadOffset: BinaryPrimitives.ReadInt32BigEndian(span[20..24]),
                FileOffset: currentDataPos,
                IsCompressed: isCompressed
            );

            byte[] sectionBytes;
            if (isCompressed)
            {
                sectionBytes = RefPack.Decompress(packedSpan, dataSize);
            }
            else
            {
                int len = Math.Min(dataSize, readSize);
                sectionBytes = new byte[len];
                packedSpan[..len].CopyTo(sectionBytes);
            }

            var section = new StrSection
            {
                SectionIndex = i,
                Descriptor = desc
            };

            ParseSectionChunks(sectionBytes, section);
            Sections.Add(section);

            descriptorPos += 24;
            currentDataPos += readSize;
        }
    }

    private static void ParseSectionChunks(byte[] data, StrSection section)
    {
        int offset = 0;
        while (offset + 12 <= data.Length)
        {
            ushort chunkType = BinaryPrimitives.ReadUInt16BigEndian(data.AsSpan(offset, 2));
            int recordSize = BinaryPrimitives.ReadInt32LittleEndian(data.AsSpan(offset + 4, 4));
            if (recordSize <= 0 || offset + 12 + recordSize > data.Length)
                break;

            int bodyStart = offset + 12;
            int bodyEnd = bodyStart + recordSize;
            byte[] body = data[bodyStart..bodyEnd];

            var chunk = new StrChunk
            {
                ChunkType = chunkType,
                StartOffset = offset,
                PayloadStart = bodyStart,
                PayloadSize = recordSize,
                Data = body,
                PayloadData = body,
                TypeName = chunkType switch
                {
                    0x1607 => "Embedded Asset",
                    0x2207 => "SimGroup",
                    _ => $"Unknown (0x{chunkType:04X})"
                }
            };

            if (chunkType == 0x1607 && body.Length >= 4)
            {
                uint headerSize = BinaryPrimitives.ReadUInt32BigEndian(body.AsSpan(0, 4));
                chunk.HeaderSize = (int)headerSize;
                int limit = (int)(4 + headerSize);

                if (headerSize > 0 && limit <= body.Length)
                {
                    int cursor = 4;
                    var fields = new List<string>();

                    for (int part = 0; part < 4; part++)
                    {
                        if (part == 1)
                        {
                            if (cursor + 16 <= limit)
                            {
                                chunk.AssetGuid = Convert.ToHexString(body[cursor..(cursor + 16)]);
                                cursor += 16;
                            }
                        }

                        if (cursor + 4 > limit) break;
                        uint strLen = BinaryPrimitives.ReadUInt32BigEndian(body.AsSpan(cursor, 4));
                        cursor += 4;

                        if (cursor + strLen > limit) break;
                        byte[] strBytes = body[cursor..(cursor + (int)strLen)];
                        int nullIdx = Array.IndexOf(strBytes, (byte)0);
                        int validLen = nullIdx >= 0 ? nullIdx : strBytes.Length;
                        fields.Add(Encoding.ASCII.GetString(strBytes, 0, validLen));
                        cursor += (int)strLen;
                    }

                    if (fields.Count > 0) chunk.FileName = fields[0];
                    if (fields.Count > 1) chunk.ResourceType = fields[1];
                    if (fields.Count > 2) chunk.FullPath = fields[2];
                    if (fields.Count > 3) chunk.ExtraString = fields[3];

                    if (cursor + 8 <= limit)
                    {
                        int payloadSize = BinaryPrimitives.ReadInt32BigEndian(body.AsSpan(cursor + 4, 4));
                        if (limit + payloadSize <= body.Length)
                        {
                            chunk.PayloadStart = bodyStart + limit;
                            chunk.PayloadSize = payloadSize;
                            chunk.PayloadData = body[limit..(limit + payloadSize)];
                        }
                    }
                }
            }

            section.Chunks.Add(chunk);
            offset = bodyEnd;
        }
    }
}
