using System.ComponentModel;
using System.Runtime.CompilerServices;
using TheSimpsonsGame.FileViewer.IO;

namespace TheSimpsonsGame.FileViewer.UI.Models;

public class FileTreeItem : INotifyPropertyChanged
{
    private bool _isOpen;
    private bool _isSelected;
    private string _colorTag = "unknown";

    public string Name { get; set; } = string.Empty;
    public string FullPath { get; set; } = string.Empty;
    public bool IsDirectory { get; set; }
    public bool IsFile { get; set; }
    public bool IsArchive { get; set; }
    public bool IsAsset { get; set; }
    public bool IsSimGroup { get; set; }
    public StrChunk? Chunk { get; set; }
    public byte[]? PayloadData { get; set; }
    public long FileSize { get; set; }
    public bool IsLoaded { get; set; }
    public bool IsDeferred { get; set; }

    public FileTreeItem? Parent { get; set; }
    public List<FileTreeItem> Children { get; } = new();

    public string ColorTag
    {
        get => _colorTag;
        set => SetField(ref _colorTag, value);
    }

    public bool IsOpen
    {
        get => _isOpen;
        set => SetField(ref _isOpen, value);
    }

    public bool IsSelected
    {
        get => _isSelected;
        set => SetField(ref _isSelected, value);
    }

    public event PropertyChangedEventHandler? PropertyChanged;

    protected void OnPropertyChanged([CallerMemberName] string? propertyName = null)
        => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));

    protected bool SetField<T>(ref T field, T value, [CallerMemberName] string? propertyName = null)
    {
        if (EqualityComparer<T>.Default.Equals(field, value)) return false;
        field = value;
        OnPropertyChanged(propertyName);
        return true;
    }
}
