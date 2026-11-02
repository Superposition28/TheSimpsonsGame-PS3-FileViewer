using System.Buffers.Binary;
using System.Security.Cryptography;
using System.Text;

namespace TheSimpsonsGame.FileViewer.IO;

/// <summary>ELF32 big-endian EM_SPU metadata. All file offsets in this object are relative to its own ELF header.</summary>
public sealed class SpuElfInfo
{
    public string CoordinateSystem => "ELF-relative file offsets; SPU virtual addresses. These are not PPU addresses.";
    public SpuElfHeader Header { get; private set; } = null!;
    public ulong EntryFileOffset { get; private set; }
    public ulong DeclaredSize { get; private set; }
    public string DeclaredSha256 { get; private set; } = "";
    public List<ElfProgramHeader> ProgramHeaders { get; } = new();
    public List<ElfSectionHeader> SectionHeaders { get; } = new();
    public Dictionary<int, string> SectionNames { get; } = new();
    public List<ElfNoteInfo> Notes { get; } = new();
    public string Limitation => "Declared extent includes headers/tables and file-backed section/segment ranges, including interior gaps; excludes trailing embedding alignment. Metadata labels do not establish workload, execution, instruction coverage or a PPU/SPU argument contract.";

    internal static bool IsSpuHeader(ReadOnlySpan<byte> data) => data.Length >= 20 &&
        data[0] == 0x7f && data[1] == (byte)'E' && data[2] == (byte)'L' && data[3] == (byte)'F' &&
        data[4] == 1 && data[5] == 2 && data[6] == 1 &&
        BinaryPrimitives.ReadUInt16BigEndian(data.Slice(18, 2)) == 23;

    internal static SpuElfInfo Parse(byte[] carrier, ulong sourceOffset, ulong sourceLimit)
    {
        if (sourceOffset > sourceLimit || sourceLimit > (ulong)carrier.LongLength)
            throw new InvalidDataException("Invalid SPU carrier bounds.");
        ulong available = sourceLimit - sourceOffset, extent = 0;
        int At(ulong offset, ulong size, string label, bool countExtent = true)
        {
            if (offset > available || size > available - offset)
                throw new InvalidDataException($"SPU {label} exceeds initialized carrier/file boundary.");
            if (countExtent && size > 0) extent = Math.Max(extent, offset + size);
            return checked((int)(sourceOffset + offset));
        }
        At(0, 52, "header");
        if (!IsSpuHeader(carrier.AsSpan((int)sourceOffset, (int)Math.Min(available, 52))))
            throw new InvalidDataException("Expected ELF32 big-endian version 1 EM_SPU header.");
        ushort U16(ulong offset) => BinaryPrimitives.ReadUInt16BigEndian(carrier.AsSpan(At(offset, 2, "header field"), 2));
        uint U32(ulong offset) => BinaryPrimitives.ReadUInt32BigEndian(carrier.AsSpan(At(offset, 4, "header field"), 4));
        var h = new SpuElfHeader(Convert.ToHexStringLower(carrier.AsSpan((int)sourceOffset, 16)),
            carrier[(int)sourceOffset + 7], U16(16), U16(18), U32(20), U32(24), U32(28), U32(32), U32(36),
            U16(40), U16(42), U16(44), U16(46), U16(48), U16(50));
        if (h.Type != 2 || h.Version != 1 || h.HeaderSize != 52 || h.ProgramHeaderSize != 32 ||
            h.ProgramHeaderCount is 0 or 0xffff || h.SectionHeaderSize != 40 || h.SectionHeaderCount == 0 ||
            h.SectionNameIndex == 0 || h.SectionNameIndex == 0xffff || h.SectionNameIndex >= h.SectionHeaderCount)
            throw new InvalidDataException("Unsupported SPU ELF32 header/table profile (ordinary ET_EXEC tables and section names required).");
        At(h.ProgramHeaderOffset, (ulong)h.ProgramHeaderSize * h.ProgramHeaderCount, "program-header table");
        At(h.SectionHeaderOffset, (ulong)h.SectionHeaderSize * h.SectionHeaderCount, "section-header table");
        var image = new SpuElfInfo { Header = h };
        for (int i = 0; i < h.ProgramHeaderCount; i++)
        {
            ulong at = h.ProgramHeaderOffset + (ulong)i * 32;
            var ph = new ElfProgramHeader(i, U32(at), U32(at + 24), U32(at + 4), U32(at + 8), U32(at + 12),
                U32(at + 16), U32(at + 20), U32(at + 28));
            At(ph.FileOffset, ph.FileSize, $"PH[{i}] file range");
            Require32BitRange(ph.VirtualAddress, ph.MemorySize, $"PH[{i}] memory range");
            if (ph.Type == 1 && ph.FileSize > ph.MemorySize)
                throw new InvalidDataException($"SPU PH[{i}] filesz exceeds memsz.");
            image.ProgramHeaders.Add(ph);
        }
        for (int i = 0; i < h.SectionHeaderCount; i++)
        {
            ulong at = h.SectionHeaderOffset + (ulong)i * 40;
            var sh = new ElfSectionHeader(i, U32(at), U32(at + 4), U32(at + 8), U32(at + 12), U32(at + 16),
                U32(at + 20), U32(at + 24), U32(at + 28), U32(at + 32), U32(at + 36));
            Require32BitRange(sh.VirtualAddress, sh.Size, $"SH[{i}] memory range");
            if (sh.Type != 8) At(sh.FileOffset, sh.Size, $"SH[{i}] file range");
            image.SectionHeaders.Add(sh);
        }
        var names = image.SectionHeaders[h.SectionNameIndex];
        if (names.Type != 3 || names.Size == 0)
            throw new InvalidDataException("SPU section-name table is not a nonempty SHT_STRTAB.");
        int namesAt = At(names.FileOffset, names.Size, "section-name table");
        foreach (var sh in image.SectionHeaders)
        {
            if (sh.NameOffset >= names.Size) throw new InvalidDataException("SPU section-name offset outside string table.");
            int begin = checked(namesAt + (int)sh.NameOffset);
            int remaining = checked((int)(names.Size - sh.NameOffset));
            int length = carrier.AsSpan(begin, remaining).IndexOf((byte)0);
            if (length < 0) throw new InvalidDataException("Unterminated SPU section name.");
            image.SectionNames.Add(sh.Index, Encoding.UTF8.GetString(carrier, begin, length));
        }

        var noteRanges = new HashSet<(ulong Offset, ulong Size)>();
        foreach (var ph in image.ProgramHeaders.Where(ph => ph.Type == 4 && ph.FileSize > 0))
            noteRanges.Add((ph.FileOffset, ph.FileSize));
        foreach (var sh in image.SectionHeaders.Where(sh => sh.Type == 7 && sh.Size > 0))
            noteRanges.Add((sh.FileOffset, sh.Size));
        foreach (var (offset, size) in noteRanges.OrderBy(r => r.Offset).ThenBy(r => r.Size))
        {
            At(offset, size, "note range");
            ulong cursor = offset, end = offset + size;
            while (cursor < end)
            {
                if (end - cursor < 12) throw new InvalidDataException("Truncated SPU ELF note header.");
                uint nameSize = U32(cursor), descriptorSize = U32(cursor + 4), type = U32(cursor + 8);
                ulong nameStart = cursor + 12;
                ulong descriptorStart = Align4(nameStart + nameSize);
                ulong next = Align4(descriptorStart + descriptorSize);
                if (nameStart + nameSize > end || next > end)
                    throw new InvalidDataException("Truncated SPU ELF note contents/padding.");
                int nameAt = At(nameStart, nameSize, "note owner");
                int descriptorAt = At(descriptorStart, descriptorSize, "note descriptor");
                var nameBytes = carrier.AsSpan(nameAt, (int)nameSize);
                var descriptorBytes = carrier.AsSpan(descriptorAt, (int)descriptorSize);
                var note = new ElfNoteInfo(cursor, type, nameSize, descriptorSize,
                    Convert.ToHexStringLower(nameBytes), TextPrefix(nameBytes),
                    Convert.ToHexStringLower(descriptorBytes), TextPrefix(descriptorBytes), descriptorBytes.Contains((byte)0));
                // PT_NOTE and SHT_NOTE often describe the same stored note.
                if (!image.Notes.Any(existing => existing.NestedFileOffset == cursor)) image.Notes.Add(note);
                cursor = next;
            }
        }
        if ((h.EntryAddress & 3) != 0) throw new InvalidDataException("SPU entry is not word-aligned.");
        image.EntryFileOffset = image.MapVirtualAddress(h.EntryAddress, 4);
        if (!image.ProgramHeaders.Any(ph => ph.Type == 1 && (ph.Flags & 1) != 0 && h.EntryAddress >= ph.VirtualAddress &&
            h.EntryAddress - ph.VirtualAddress < ph.FileSize))
            throw new InvalidDataException("SPU entry is not in an executable file-backed PT_LOAD.");
        image.DeclaredSize = extent;
        image.DeclaredSha256 = Convert.ToHexStringLower(SHA256.HashData(carrier.AsSpan((int)sourceOffset, (int)extent)));
        return image;
    }

    public ulong MapVirtualAddress(ulong address, ulong length) => Ps3ExecutableInfo.MapVirtualAddressCore(ProgramHeaders, address, length);

    internal static void Discover(byte[] carrier, Ps3ExecutableInfo parent)
    {
        var supportedCandidates = new List<ulong>();
        for (int i = 0; i <= carrier.Length - 20; i++)
            if (carrier[i] == 0x7f && IsSpuHeader(carrier.AsSpan(i, 20))) supportedCandidates.Add((ulong)i);
        var validated = new List<EmbeddedSpuImage>();
        foreach (ulong offset in supportedCandidates)
        {
            try
            {
                var owners = parent.ProgramHeaders.Where(ph => ph.Type == 1 && offset >= ph.FileOffset &&
                    offset - ph.FileOffset < ph.FileSize).ToList();
                if (owners.Count != 1) throw new InvalidDataException("SPU header does not have exactly one initialized parent PT_LOAD owner.");
                var owner = owners[0];
                var image = Parse(carrier, offset, owner.FileOffset + owner.FileSize);
                ulong ppuAddress = owner.VirtualAddress + offset - owner.FileOffset;
                if (parent.MapVirtualAddress(ppuAddress, image.DeclaredSize) != offset)
                    throw new InvalidDataException("SPU declared extent disagrees with parent PT_LOAD mapping.");
                validated.Add(new EmbeddedSpuImage(offset, ppuAddress, owner.Index, image));
            }
            catch (InvalidDataException ex)
            {
                parent.RejectedSpuCandidates.Add(new(offset, ex.Message));
            }
        }
        foreach (var image in validated)
        {
            if (validated.Any(other => other.CarrierFileOffset != image.CarrierFileOffset &&
                image.CarrierFileOffset < other.CarrierFileOffset + other.Image.DeclaredSize &&
                other.CarrierFileOffset < image.CarrierFileOffset + image.Image.DeclaredSize))
                parent.RejectedSpuCandidates.Add(new(image.CarrierFileOffset, "Structurally valid SPU extent overlaps another validated SPU candidate; ambiguous embedding rejected."));
            else parent.EmbeddedSpuImages.Add(image);
        }
    }

    private static void Require32BitRange(ulong address, ulong size, string label)
    {
        if (address + size > 0x100000000UL) throw new InvalidDataException($"SPU {label} wraps its 32-bit address space.");
    }
    private static ulong Align4(ulong value) => (value + 3) & ~3UL;
    private static string TextPrefix(ReadOnlySpan<byte> bytes)
    {
        int nul = bytes.IndexOf((byte)0);
        return Encoding.ASCII.GetString(nul < 0 ? bytes : bytes[..nul]);
    }
}

public sealed record SpuElfHeader(string IdentHex, byte OsAbi, ushort Type, ushort Machine, uint Version, uint EntryAddress,
    uint ProgramHeaderOffset, uint SectionHeaderOffset, uint Flags, ushort HeaderSize, ushort ProgramHeaderSize,
    ushort ProgramHeaderCount, ushort SectionHeaderSize, ushort SectionHeaderCount, ushort SectionNameIndex);

public sealed record ElfNoteInfo(ulong NestedFileOffset, uint Type, uint OwnerSize, uint DescriptorSize,
    string OwnerHex, string OwnerText, string DescriptorHex, string DescriptorText, bool DescriptorHasNul);

public sealed record EmbeddedSpuImage(ulong CarrierFileOffset, ulong ParentPpuCarrierVirtualAddress,
    int ParentPtLoadIndex, SpuElfInfo Image)
{
    public string CoordinateSystem => "CarrierFileOffset is in the parent PPU ELF file; ParentPpuCarrierVirtualAddress maps the header bytes only. Image offsets/addresses are in the separate nested SPU ELF namespace. Parent file offset = CarrierFileOffset + Image nested file offset.";
}

public sealed record RejectedSpuCandidate(ulong CarrierFileOffset, string Reason);
