using System.Buffers.Binary;
using System.Security.Cryptography;

namespace TheSimpsonsGame.FileViewer.IO;

/// <summary>Read-only stored metadata. This reader neither decrypts nor executes an executable.</summary>
public sealed class Ps3ExecutableInfo
{
    public string Kind { get; private set; } = "";
    public long FileSize { get; private set; }
    public string Sha256 { get; private set; } = "";
    public uint? SceVersion { get; private set; }
    public string Limitation { get; private set; } = "";
    public byte? OsAbi { get; private set; }
    public ushort? ElfType { get; private set; }
    public ushort? Machine { get; private set; }
    public ulong? EntryDescriptorAddress { get; private set; }
    public ulong? EntryDescriptorFileOffset { get; private set; }
    public uint? EntryCodeAddress { get; private set; }
    public uint? EntryToc { get; private set; }
    public ulong? SectionNameTableSize { get; private set; }
    public bool? SectionNameTableZeroFilled { get; private set; }
    public int TypedSymbolSections { get; private set; }
    public int? DescriptorTableCandidateSection { get; private set; }
    public int ValidDescriptorCandidates { get; private set; }
    public int ZeroDescriptorSlots { get; private set; }
    public int InvalidDescriptorSlots { get; private set; }
    public Dictionary<string, int> DescriptorTocCounts { get; } = new();
    public List<ElfProgramHeader> ProgramHeaders { get; } = new();
    public List<ElfSectionHeader> SectionHeaders { get; } = new();
    public SpuElfInfo? SpuImage { get; private set; }
    public List<EmbeddedSpuImage> EmbeddedSpuImages { get; } = new();
    public List<RejectedSpuCandidate> RejectedSpuCandidates { get; } = new();

    public static Ps3ExecutableInfo Load(string path) => Parse(File.ReadAllBytes(path));

    public static Ps3ExecutableInfo Parse(byte[] data)
    {
        ArgumentNullException.ThrowIfNull(data);
        var info = new Ps3ExecutableInfo
        {
            FileSize = data.LongLength,
            Sha256 = Convert.ToHexStringLower(SHA256.HashData(data))
        };
        if (data.AsSpan().StartsWith("SCE\0"u8))
        {
            RequireRange(data, 0, 32, "SCE common header");
            info.Kind = "SCE wrapper";
            info.SceVersion = U32(data, 4);
            info.Limitation = "Outer signature/version only. Payload encryption, signatures and embedded ELF are not decoded or validated.";
            return info;
        }

        if (SpuElfInfo.IsSpuHeader(data))
        {
            var image = SpuElfInfo.Parse(data, 0, (ulong)data.LongLength);
            info.Kind = "SPU ELF32 big-endian";
            info.SpuImage = image;
            info.OsAbi = image.Header.OsAbi;
            info.ElfType = image.Header.Type;
            info.Machine = image.Header.Machine;
            info.EntryCodeAddress = image.Header.EntryAddress;
            info.ProgramHeaders.AddRange(image.ProgramHeaders);
            info.SectionHeaders.AddRange(image.SectionHeaders);
            info.TypedSymbolSections = image.SectionHeaders.Count(sh => sh.Type is 2 or 11);
            info.Limitation = image.Limitation;
            return info;
        }

        RequireRange(data, 0, 64, "ELF64 header");
        if (!(data[0] == 0x7f && data[1] == (byte)'E' && data[2] == (byte)'L' && data[3] == (byte)'F'))
            throw new InvalidDataException("Expected an ELF or SCE signature.");
        if (data[4] != 2 || data[5] != 2 || data[6] != 1 || data[7] != 0x66 ||
            U16(data, 16) != 2 || U16(data, 18) != 21 || U32(data, 20) != 1)
            throw new InvalidDataException("Supported ELF profile: PS3 (OSABI 0x66), ELF64, big-endian, version 1, ET_EXEC, EM_PPC64.");
        if (U16(data, 52) != 64)
            throw new InvalidDataException("Unexpected ELF64 header size.");

        info.Kind = "PS3 ELF64 big-endian PPC64";
        info.OsAbi = data[7];
        info.ElfType = U16(data, 16);
        info.Machine = U16(data, 18);
        info.EntryDescriptorAddress = U64(data, 24);
        ulong phOffset = U64(data, 32), shOffset = U64(data, 40);
        ushort phSize = U16(data, 54), phCount = U16(data, 56);
        ushort shSize = U16(data, 58), shCount = U16(data, 60), shNames = U16(data, 62);
        if (phCount == 0 || phCount == 0xffff || phSize != 56 ||
            (shCount == 0 && shOffset != 0) || shNames == 0xffff ||
            (shCount > 0 && (shSize != 64 || shNames >= shCount)))
            throw new InvalidDataException("Invalid or unsupported ELF table sizes/extended numbering.");
        RequireRange(data, phOffset, (ulong)phSize * phCount, "program-header table");
        if (shCount > 0) RequireRange(data, shOffset, (ulong)shSize * shCount, "section-header table");

        for (int i = 0; i < phCount; i++)
        {
            int at = checked((int)(phOffset + (ulong)i * phSize));
            var ph = new ElfProgramHeader(i, U32(data, at), U32(data, at + 4),
                U64(data, at + 8), U64(data, at + 16), U64(data, at + 24),
                U64(data, at + 32), U64(data, at + 40), U64(data, at + 48));
            RequireRange(data, ph.FileOffset, ph.FileSize, $"PH[{i}] file range");
            RequireNoOverflow(ph.VirtualAddress, ph.MemorySize, $"PH[{i}] memory range");
            if (ph.Type == 1 && ph.FileSize > ph.MemorySize)
                throw new InvalidDataException($"PH[{i}] file size exceeds its loadable memory size.");
            info.ProgramHeaders.Add(ph);
        }

        for (int i = 0; i < shCount; i++)
        {
            int at = checked((int)(shOffset + (ulong)i * shSize));
            var sh = new ElfSectionHeader(i, U32(data, at), U32(data, at + 4), U64(data, at + 8),
                U64(data, at + 16), U64(data, at + 24), U64(data, at + 32),
                U32(data, at + 40), U32(data, at + 44), U64(data, at + 48), U64(data, at + 56));
            RequireNoOverflow(sh.VirtualAddress, sh.Size, $"SH[{i}] memory range");
            if (sh.Type != 8) RequireRange(data, sh.FileOffset, sh.Size, $"SH[{i}] file range");
            info.SectionHeaders.Add(sh);
            if (sh.Type is 2 or 11) info.TypedSymbolSections++;
        }
        if (shCount > 0 && shNames != 0)
        {
            var names = info.SectionHeaders[shNames];
            if (names.Type != 3) throw new InvalidDataException("Section-name table is not SHT_STRTAB.");
            info.SectionNameTableSize = names.Size;
            info.SectionNameTableZeroFilled = data.AsSpan((int)names.FileOffset, (int)names.Size).IndexOfAnyExcept((byte)0) < 0;
        }

        ulong entryOffset = info.MapVirtualAddress(info.EntryDescriptorAddress.Value, 8);
        info.EntryDescriptorFileOffset = entryOffset;
        info.EntryCodeAddress = U32(data, checked((int)entryOffset));
        info.EntryToc = U32(data, checked((int)entryOffset + 4));
        info.RequireExecutableAddress(info.EntryCodeAddress.Value);
        info.MapVirtualAddress(info.EntryToc.Value, 1);

        var tables = info.SectionHeaders.Where(sh => sh.Type == 1 && (sh.Flags & 1) != 0 &&
            sh.Size % 8 == 0 && info.EntryDescriptorAddress >= sh.VirtualAddress &&
            info.EntryDescriptorAddress - sh.VirtualAddress <= sh.Size &&
            8 <= sh.Size - (info.EntryDescriptorAddress.Value - sh.VirtualAddress)).ToList();
        if (tables.Count == 1)
        {
            var table = tables[0];
            if (info.MapVirtualAddress(table.VirtualAddress, table.Size) != table.FileOffset)
                throw new InvalidDataException("Descriptor candidate section disagrees with PT_LOAD mapping.");
            info.DescriptorTableCandidateSection = table.Index;
            for (ulong offset = 0; offset < table.Size; offset += 8)
            {
                int at = checked((int)(table.FileOffset + offset));
                uint code = U32(data, at), toc = U32(data, at + 4);
                if (code == 0 && toc == 0) { info.ZeroDescriptorSlots++; continue; }
                try { info.RequireExecutableAddress(code); info.MapVirtualAddress(toc, 1); }
                catch (InvalidDataException) { info.InvalidDescriptorSlots++; continue; }
                info.ValidDescriptorCandidates++;
                string key = $"0x{toc:X8}";
                info.DescriptorTocCounts[key] = info.DescriptorTocCounts.GetValueOrDefault(key) + 1;
            }
        }
        info.Limitation = "Stored headers and descriptor candidates only. No original symbol names, runtime execution, import binding or semantic completeness is established.";
        SpuElfInfo.Discover(data, info);
        return info;
    }

    /// <summary>Map a complete nonempty range through exactly one PT_LOAD. Gaps, overlaps and zero-fill fail.</summary>
    public ulong MapVirtualAddress(ulong address, ulong length)
    {
        if (Kind != "PS3 ELF64 big-endian PPC64" && Kind != "SPU ELF32 big-endian")
            throw new InvalidDataException("Mapping requires an ELF and a nonempty byte range.");
        return MapVirtualAddressCore(ProgramHeaders, address, length);
    }

    internal static ulong MapVirtualAddressCore(IReadOnlyList<ElfProgramHeader> programHeaders, ulong address, ulong length)
    {
        if (length == 0) throw new InvalidDataException("Mapping requires a nonempty byte range.");
        RequireNoOverflow(address, length, "requested virtual range");
        ulong end = address + length;
        var matches = programHeaders.Where(ph => ph.Type == 1 && ph.MemorySize > 0 &&
            address < ph.VirtualAddress + ph.MemorySize && end > ph.VirtualAddress).ToList();
        if (matches.Count != 1)
            throw new InvalidDataException("Virtual range is unmapped, crosses a gap or overlaps multiple PT_LOAD segments.");
        var segment = matches[0];
        if (address < segment.VirtualAddress)
            throw new InvalidDataException("Virtual range begins outside its PT_LOAD.");
        ulong delta = address - segment.VirtualAddress;
        if (delta > segment.FileSize || length > segment.FileSize - delta)
            throw new InvalidDataException("Virtual range is not entirely file-backed (gap, segment end or zero-fill).");
        return segment.FileOffset + delta;
    }

    private void RequireExecutableAddress(uint address)
    {
        if ((address & 3) != 0) throw new InvalidDataException("Descriptor code address is not word-aligned.");
        MapVirtualAddress(address, 4);
        if (!ProgramHeaders.Any(ph => ph.Type == 1 && (ph.Flags & 1) != 0 && address >= ph.VirtualAddress &&
            (ulong)address - ph.VirtualAddress < ph.FileSize))
            throw new InvalidDataException("Descriptor code address is not in an executable PT_LOAD.");
    }

    private static ushort U16(byte[] data, int offset) => BinaryPrimitives.ReadUInt16BigEndian(data.AsSpan(offset, 2));
    private static uint U32(byte[] data, int offset) => BinaryPrimitives.ReadUInt32BigEndian(data.AsSpan(offset, 4));
    private static ulong U64(byte[] data, int offset) => BinaryPrimitives.ReadUInt64BigEndian(data.AsSpan(offset, 8));

    private static void RequireRange(byte[] data, ulong offset, ulong size, string label)
    {
        if (offset > (ulong)data.LongLength || size > (ulong)data.LongLength - offset)
            throw new InvalidDataException($"Truncated/out-of-range {label}.");
    }

    private static void RequireNoOverflow(ulong start, ulong size, string label)
    {
        if (size > ulong.MaxValue - start) throw new InvalidDataException($"Overflow in {label}.");
    }
}

public sealed record ElfProgramHeader(int Index, uint Type, uint Flags, ulong FileOffset,
    ulong VirtualAddress, ulong PhysicalAddress, ulong FileSize, ulong MemorySize, ulong Alignment);

public sealed record ElfSectionHeader(int Index, uint NameOffset, uint Type, ulong Flags,
    ulong VirtualAddress, ulong FileOffset, ulong Size, uint Link, uint Info, ulong Alignment, ulong EntrySize);
