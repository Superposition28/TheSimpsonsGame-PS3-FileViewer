using System.Text.Json.Serialization;

namespace TheSimpsonsGame.FileViewer.Formats;

public class IdentifierItem
{
    [JsonPropertyName("id")]
    public long Id { get; set; }

    [JsonPropertyName("namespace")]
    public string Namespace { get; set; } = string.Empty;

    [JsonPropertyName("value")]
    public string Value { get; set; } = string.Empty;

    [JsonPropertyName("role")]
    public string Role { get; set; } = string.Empty;

    [JsonPropertyName("offset")]
    public int Offset { get; set; }

    [JsonPropertyName("width")]
    public int Width { get; set; }

    [JsonPropertyName("endian")]
    public string Endian { get; set; } = "BE";

    [JsonPropertyName("label")]
    public string Label { get; set; } = string.Empty;

    [JsonPropertyName("confidence")]
    public string Confidence { get; set; } = "structural";

    [JsonPropertyName("doc")]
    public string Doc { get; set; } = string.Empty;

    [JsonPropertyName("region")]
    public string Region { get; set; } = "payload";

    [JsonPropertyName("resolution")]
    public object? Resolution { get; set; }
}

public class TreeNodeModel
{
    [JsonPropertyName("label")]
    public string Label { get; set; } = string.Empty;

    [JsonPropertyName("children")]
    public List<TreeNodeModel> Children { get; set; } = new();

    public TreeNodeModel() { }

    public TreeNodeModel(string label, List<TreeNodeModel>? children = null)
    {
        Label = label;
        Children = children ?? new();
    }
}

public class TableDataModel
{
    [JsonPropertyName("headers")]
    public List<string> Headers { get; set; } = new();

    [JsonPropertyName("rows")]
    public List<List<string>> Rows { get; set; } = new();

    [JsonPropertyName("summary")]
    public string Summary { get; set; } = string.Empty;
}

public class TextureImageInfo
{
    public string Name { get; set; } = string.Empty;
    public int Width { get; set; }
    public int Height { get; set; }
    public string FormatName { get; set; } = string.Empty;
    public byte FormatCode { get; set; }
    public int MipCount { get; set; }
    public byte[] RgbaPixels { get; set; } = Array.Empty<byte>();
    public byte[] DdsBytes { get; set; } = Array.Empty<byte>();
}

public class ParsedResource
{
    [JsonPropertyName("format")]
    public string Format { get; set; } = string.Empty;

    [JsonPropertyName("summary")]
    public string Summary { get; set; } = string.Empty;

    [JsonPropertyName("structure")]
    public object? Structure { get; set; }

    [JsonPropertyName("identifiers")]
    public List<IdentifierItem> Identifiers { get; set; } = new();

    [JsonPropertyName("identifier_status")]
    public string IdentifierStatus { get; set; } = "no structural IDs extracted";

    [JsonPropertyName("tree")]
    public List<TreeNodeModel>? Tree { get; set; }

    [JsonIgnore]
    public TableDataModel? Table { get; set; }

    [JsonIgnore]
    public List<TextureImageInfo>? Textures { get; set; }

    [JsonIgnore]
    public string? RawText { get; set; }
}

