using Avalonia.Media;

namespace TheSimpsonsGame.FileViewer.UI.Models;

public class AsciiTreeRow
{
    private static readonly IBrush DuplicateBrush = SolidColorBrush.Parse("#E3B341");
    private static readonly IBrush UniqueBrush = SolidColorBrush.Parse("#56D879");
    private static readonly IBrush EmptyBrush = SolidColorBrush.Parse("#FF7B72");
    private static readonly IBrush UnknownBrush = SolidColorBrush.Parse("#B0BAC5");
    private static readonly IBrush DefaultBrush = SolidColorBrush.Parse("#C9D1D9");

    public string Prefix { get; set; } = string.Empty;
    public string Label { get; set; } = string.Empty;
    public string ColorTag { get; set; } = "tree_default";
    public FileTreeItem? Node { get; set; }
    public bool IsSelectable => Node != null;

    public IBrush LabelBrush => ColorTag switch
    {
        "duplicate" or "asset_partial" => DuplicateBrush,
        "unique" or "asset_supported" => UniqueBrush,
        "empty" or "asset_hex_only" => EmptyBrush,
        "unknown" or "asset_unknown" => UnknownBrush,
        _ => DefaultBrush
    };

    public string FullText => string.IsNullOrEmpty(Label) ? Prefix : $"{Prefix}{Label}";
}

