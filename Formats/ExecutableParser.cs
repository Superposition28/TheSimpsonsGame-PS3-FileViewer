using TheSimpsonsGame.FileViewer.IO;

namespace TheSimpsonsGame.FileViewer.Formats;

public static class ExecutableParser
{
    public static TreeNodeModel ToTreeNode(Ps3ExecutableInfo info)
    {
        var root = new TreeNodeModel($"{info.Kind} ({info.FileSize:N0} bytes)");
        root.Children.Add(new($"SHA-256: {info.Sha256}"));
        if (info.SceVersion.HasValue)
            root.Children.Add(new($"SCE version: {info.SceVersion}"));
        if (info.SpuImage != null)
            root.Children.Add(SpuTree(info.SpuImage));
        if (info.EntryDescriptorAddress.HasValue)
        {
            root.Children.Add(new($"e_entry descriptor: VA 0x{info.EntryDescriptorAddress:X8}, file 0x{info.EntryDescriptorFileOffset:X8}"));
            root.Children.Add(new($"Entry code: 0x{info.EntryCodeAddress:X8}; TOC: 0x{info.EntryToc:X8}"));
            root.Children.Add(new($"Typed ELF symbol sections: {info.TypedSymbolSections}"));
            root.Children.Add(new($"Section-name string table zero-filled: {info.SectionNameTableZeroFilled}"));
            var headers = new TreeNodeModel($"Program headers ({info.ProgramHeaders.Count}); ends exclusive");
            foreach (var ph in info.ProgramHeaders)
                headers.Children.Add(new($"PH[{ph.Index}] type 0x{ph.Type:X8}, flags 0x{ph.Flags:X8}; file [0x{ph.FileOffset:X}, 0x{ph.FileOffset + ph.FileSize:X}); VA [0x{ph.VirtualAddress:X}, 0x{ph.VirtualAddress + ph.MemorySize:X}); file size 0x{ph.FileSize:X}, memory size 0x{ph.MemorySize:X}, alignment 0x{ph.Alignment:X}"));
            root.Children.Add(headers);
            if (info.DescriptorTableCandidateSection.HasValue)
            {
                var descriptors = new TreeNodeModel($"SH[{info.DescriptorTableCandidateSection}] descriptor-table candidate: {info.ValidDescriptorCandidates:N0} valid, {info.ZeroDescriptorSlots} zero, {info.InvalidDescriptorSlots} invalid slots");
                foreach (var (toc, count) in info.DescriptorTocCounts)
                    descriptors.Children.Add(new($"TOC {toc}: {count:N0} candidates"));
                root.Children.Add(descriptors);
            }
            var sections = new TreeNodeModel($"Section headers ({info.SectionHeaders.Count}); names are not synthesized");
            foreach (var sh in info.SectionHeaders)
                sections.Children.Add(new($"SH[{sh.Index}] type {sh.Type}, flags 0x{sh.Flags:X}, VA 0x{sh.VirtualAddress:X}, file 0x{sh.FileOffset:X}, size 0x{sh.Size:X}"));
            root.Children.Add(sections);
        }
        if (info.EmbeddedSpuImages.Count > 0)
        {
            var images = new TreeNodeModel($"Validated embedded SPU ELFs ({info.EmbeddedSpuImages.Count}); SPU addresses use separate namespaces");
            foreach (var embedded in info.EmbeddedSpuImages)
            {
                var image = new TreeNodeModel($"Carrier file [0x{embedded.CarrierFileOffset:X}, 0x{embedded.CarrierFileOffset + embedded.Image.DeclaredSize:X}); PPU header VA 0x{embedded.ParentPpuCarrierVirtualAddress:X8}; parent PT_LOAD {embedded.ParentPtLoadIndex}");
                image.Children.Add(SpuTree(embedded.Image, embedded.CarrierFileOffset));
                images.Children.Add(image);
            }
            root.Children.Add(images);
        }
        if (info.RejectedSpuCandidates.Count > 0)
            root.Children.Add(new($"Rejected SPU profile candidates ({info.RejectedSpuCandidates.Count})",
                info.RejectedSpuCandidates.Select(candidate => new TreeNodeModel($"Carrier file 0x{candidate.CarrierFileOffset:X}: {candidate.Reason}")).ToList()));
        root.Children.Add(new(info.Limitation));
        return root;
    }

    private static TreeNodeModel SpuTree(SpuElfInfo image, ulong carrierOffset = 0)
    {
        var root = new TreeNodeModel($"SPU ELF32 BE EM_SPU: entry SPU VA 0x{image.Header.EntryAddress:X}, nested file 0x{image.EntryFileOffset:X}; declared extent 0x{image.DeclaredSize:X} bytes");
        root.Children.Add(new($"Declared-extent SHA-256: {image.DeclaredSha256}"));
        root.Children.Add(new(image.CoordinateSystem));
        var headers = new TreeNodeModel($"SPU program headers ({image.ProgramHeaders.Count}); ends exclusive");
        foreach (var ph in image.ProgramHeaders)
            headers.Children.Add(new($"PH[{ph.Index}] type 0x{ph.Type:X}, flags 0x{ph.Flags:X}; SPU VA [0x{ph.VirtualAddress:X}, 0x{ph.VirtualAddress + ph.MemorySize:X}); nested file [0x{ph.FileOffset:X}, 0x{ph.FileOffset + ph.FileSize:X}); carrier file [0x{carrierOffset + ph.FileOffset:X}, 0x{carrierOffset + ph.FileOffset + ph.FileSize:X})"));
        root.Children.Add(headers);
        var sections = new TreeNodeModel($"SPU section headers ({image.SectionHeaders.Count}); NOBITS has no stored payload");
        foreach (var sh in image.SectionHeaders)
            sections.Children.Add(new($"SH[{sh.Index}] {image.SectionNames[sh.Index]}: type {sh.Type}, SPU VA 0x{sh.VirtualAddress:X}, size 0x{sh.Size:X}; " +
                (sh.Type == 8 ? "NOBITS (no carrier bytes)" : $"nested file 0x{sh.FileOffset:X}, carrier file 0x{carrierOffset + sh.FileOffset:X}")));
        root.Children.Add(sections);
        var notes = new TreeNodeModel($"ELF notes ({image.Notes.Count}); literal metadata labels only");
        foreach (var note in image.Notes)
        {
            var node = new TreeNodeModel($"Nested file 0x{note.NestedFileOffset:X}, carrier file 0x{carrierOffset + note.NestedFileOffset:X}; owner {note.OwnerText}, type {note.Type}; descriptor bytes {note.DescriptorSize}, NUL present {note.DescriptorHasNul}");
            node.Children.Add(new($"Descriptor text prefix: {note.DescriptorText}"));
            node.Children.Add(new($"Raw descriptor hex: {note.DescriptorHex}"));
            notes.Children.Add(node);
        }
        root.Children.Add(notes);
        root.Children.Add(new(image.Limitation));
        return root;
    }
}
