using System.Text;

namespace TheSimpsonsGame.FileViewer.Formats;

public static class ResourceDispatcher
{
    public static ParsedResource Parse(byte[] data, string name = "", string resourceType = "")
    {
        string kind = FormatDetector.Identify(name, resourceType, data);
        var result = new ParsedResource
        {
            Format = kind,
            Summary = $"{kind} resource"
        };

        if (data == null || data.Length == 0)
        {
            result.Summary = "Empty resource payload";
            return result;
        }

        try
        {
            if (kind is ".bin" or ".elf")
            {
                var executable = TheSimpsonsGame.FileViewer.IO.Ps3ExecutableInfo.Parse(data);
                result.Structure = executable;
                result.Tree = new List<TreeNodeModel> { ExecutableParser.ToTreeNode(executable) };
                result.Summary = executable.SpuImage != null
                    ? $"{executable.Kind}: SPU entry 0x{executable.EntryCodeAddress:X}; stored metadata only"
                    : executable.EntryCodeAddress.HasValue
                    ? $"{executable.Kind}: entry code 0x{executable.EntryCodeAddress:X8}, TOC 0x{executable.EntryToc:X8}"
                    : $"{executable.Kind}: version {executable.SceVersion}; outer header only";
            }
            else if (kind == ".lh2")
            {
                var table = Lh2Parser.ParseToTable(data);
                result.Table = table;
                result.Structure = table;
                result.Summary = table.Summary;
                result.Tree = new List<TreeNodeModel> { new(table.Summary) };
            }
            else if (kind == ".alb")
            {
                var table = AudioLookups.ParseAlbToTable(data);
                result.Table = table;
                result.Structure = table;
                result.Summary = table.Summary;
                result.Tree = new List<TreeNodeModel> { new(table.Summary) };
            }
            else if (kind == ".smb")
            {
                var table = AudioLookups.ParseSmbToTable(data);
                result.Table = table;
                result.Structure = table;
                result.Summary = table.Summary;
                result.Tree = new List<TreeNodeModel> { new(table.Summary) };
            }
            else if (kind == ".txd")
            {
                var textures = TxdParser.ParseTextures(data);
                result.Textures = textures;
                result.Summary = $"TXD: {textures.Count} textures found";
                result.Tree = new List<TreeNodeModel>
                {
                    new($"Texture Dictionary ({textures.Count} Textures)",
                        textures.Select(t => new TreeNodeModel($"{t.Name}: {t.Width}x{t.Height} {t.FormatName} (Mips: {t.MipCount})")).ToList())
                };
                result.Structure = textures.Select(t => new { t.Name, t.Width, t.Height, t.FormatName, t.MipCount }).ToList();
            }
            else if (kind == ".dat.simgroup" || kind == ".simgroup.dat")
            {
                var simGroup = SimGroupParser.Parse(data);
                if (simGroup != null)
                {
                    result.Structure = simGroup;
                    result.Summary = $"SimGroup: {simGroup.Entities.Count} entities, GUID {simGroup.Guid32:08X}";
                    result.Tree = new List<TreeNodeModel> { SimGroupParser.ToTreeNode(simGroup) };
                }
            }
            else if (kind == ".preinstanced")
            {
                var mesh = PreinstancedParser.Parse(data, Path.GetFileName(name));
                if (mesh != null)
                {
                    result.Structure = mesh;
                    result.Summary = $"Preinstanced Mesh: {mesh.Submeshes.Count} submeshes, {mesh.MaterialTextureNames.Count} materials";
                    result.Tree = new List<TreeNodeModel> { PreinstancedParser.ToTreeNode(mesh) };
                }
            }
            else if (kind == ".graph")
            {
                var tree = MiscParsers.ParseGraph(data);
                result.Tree = new List<TreeNodeModel> { tree };
                result.Summary = tree.Label;
            }
            else if (kind == ".meta.xml")
            {
                var tree = MiscParsers.ParseMetaModel(data);
                result.Tree = new List<TreeNodeModel> { tree };
                result.Summary = tree.Label;
            }
            else if (kind == ".cec.ps3" || kind == ".cec")
            {
                var table = MiscParsers.ParseCec(data);
                result.Table = table;
                result.Summary = table.Summary;
                result.Tree = new List<TreeNodeModel> { new(table.Summary) };
            }
            else if (kind == ".shk.ps3" || kind == ".shk")
            {
                var table = MiscParsers.ParseShk(data);
                result.Table = table;
                result.Summary = table.Summary;
                result.Tree = new List<TreeNodeModel> { new(table.Summary) };
            }
            else if (kind == ".tox.ps3" || kind == ".tob")
            {
                var table = MiscParsers.ParseTob(data);
                result.Table = table;
                result.Summary = table.Summary;
                result.Tree = new List<TreeNodeModel> { new(table.Summary) };
            }
            else if (kind == "lighttoc" || kind == ".lighttoc")
            {
                var floats = MiscParsers.ParseLightToc(data);
                result.Summary = $"LightTOC: {floats.Count} candidate floats";
                result.Tree = new List<TreeNodeModel>
                {
                    new($"LightTOC ({floats.Count} Floats)",
                        floats.Select((f, idx) => new TreeNodeModel($"[{idx}] = {f}")).ToList())
                };
            }
            else if (kind == ".hkt.ps3")
            {
                var tree = MiscParsers.ParseHavok(data);
                result.Tree = new List<TreeNodeModel> { tree };
                result.Summary = tree.Label;
            }
            else if (kind == ".msb")
            {
                var tree = MiscParsers.ParseMsb(data);
                result.Tree = new List<TreeNodeModel> { tree };
                result.Summary = tree.Label;
            }
            else if (kind is ".txt" or ".lua" or ".json" or ".xml" or ".yaml" or ".yml" or ".toml")
            {
                string text = Encoding.UTF8.GetString(data);
                result.RawText = text;
                result.Summary = $"Source text ({data.Length} bytes, UTF-8)";
                result.Tree = new List<TreeNodeModel> { new(result.Summary) };
            }
            else
            {
                string displayKind = string.IsNullOrEmpty(kind) ? "Unidentified format" : kind;
                result.Summary = $"{displayKind}: raw inspection ({data.Length} bytes)";
                result.Tree = new List<TreeNodeModel> { new(result.Summary) };
            }
        }
        catch (Exception ex)
        {
            result.Summary = $"Parser error for {kind}: {ex.Message}";
        }

        var (ids, idStatus) = IdentifierExtractor.Extract(data, kind);
        result.Identifiers = ids;
        result.IdentifierStatus = idStatus;

        return result;
    }
}
