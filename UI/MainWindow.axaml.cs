using System.Collections.Concurrent;
using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Interactivity;
using Avalonia.Media.Imaging;
using Avalonia.Platform.Storage;
using Avalonia.Threading;
using Avalonia.VisualTree;
using TheSimpsonsGame.FileViewer.Connections;
using TheSimpsonsGame.FileViewer.Formats;
using TheSimpsonsGame.FileViewer.IO;
using TheSimpsonsGame.FileViewer.Media;
using TheSimpsonsGame.FileViewer.State;
using TheSimpsonsGame.FileViewer.UI.Models;

namespace TheSimpsonsGame.FileViewer.UI;

public partial class MainWindow : Window
{
    private readonly ViewerState _state;
    private readonly string _moduleRoot;
    private readonly ServerController _server = new();
    private readonly Dictionary<string, string> _folderAliases = new(StringComparer.OrdinalIgnoreCase);

    private readonly List<FileTreeItem> _rootNodes = new();
    private readonly List<FileTreeItem> _allFiles = new();
    private int _strCount = 0;
    private string _filterPattern = string.Empty;

    private FileTreeItem? _selectedItem;
    private byte[]? _selectedBytes;
    private ParsedResource? _currentResource;
    private List<TextureImageInfo> _currentTextures = new();
    private List<string>? _currentMediaOutputs;

    private int _hexOffset = 0;
    private const int HexPageSize = 2048;
    private string _viewMode = "interpretation";

    private static readonly HashSet<string> DeferredFolders = new(StringComparer.OrdinalIgnoreCase)
    {
        "audiostreams", "a1_audio"
    };

    private static readonly HashSet<string> SkipFolders = new(StringComparer.OrdinalIgnoreCase)
    {
        ".history", ".backup", ".git", "__pycache__", ".vs", "bin", "obj"
    };

    private static readonly HashSet<string> SupportedSuffixes = new(StringComparer.OrdinalIgnoreCase)
    {
        ".str", ".lh2", ".alb", ".smb", ".dat", ".dat.uie", ".dat.simgroup", ".simgroup.dat",
        ".txt", ".lua", ".tree", ".lighttoc", ".shk", ".wav", ".ogg", ".mp3", ".flac",
        ".snr", ".ogv", ".mp4", ".avi", ".webm", ".png", ".dds", ".jpg", ".jpeg", ".bmp",
        ".tga", ".json", ".csv", ".yaml", ".yml", ".toml", ".fnt", ".srt", ".vtt", ".xml",
        ".amb", ".aub", ".bnk.ps3", ".ctb", ".mib", ".msb", ".rcb.ps3", ".rcm_b", ".sbk",
        ".toc", ".uix", ".xml.ps3", ".ps3", ".itxd", ".bin", ".elf", ".snu", ".vp6",
        ".graph", ".meta.xml", ".cec.ps3", ".shk.ps3", ".preinstanced", ".txd", ".rws", ".dff", ".tob",
        ".mus", ".sns", ".inf", ".imb", ".vfb", ".bsp", ".bbn.ps3", ".acs.ps3", ".hkt.ps3", ".hko.ps3",
        ".blend", ".glb"
    };

    public MainWindow()
    {
        InitializeComponent();

        _moduleRoot = ResolveModuleRoot();
        _state = ViewerState.Load(_moduleRoot);
        _folderAliases = LoadFolderAliases(_moduleRoot);

        // Preload AudioMap in background
        Task.Run(() => AudioMapRegistry.Instance.EnsureLoaded(_moduleRoot));

        UpdateServerStatus();

        if (!string.IsNullOrEmpty(Program.StartupPath))
        {
            if (Directory.Exists(Program.StartupPath))
            {
                OpenDirectory(Program.StartupPath);
            }
            else if (File.Exists(Program.StartupPath))
            {
                LoadSingleFile(Program.StartupPath);
            }
        }
        else if (!string.IsNullOrEmpty(_state.LastOpenedFolder) && Directory.Exists(_state.LastOpenedFolder))
        {
            OpenDirectory(_state.LastOpenedFolder);
        }
    }

    private static string ResolveModuleRoot()
    {
        string current = AppContext.BaseDirectory;
        while (!string.IsNullOrEmpty(current))
        {
            if (File.Exists(Path.Combine(current, "operations.toml")) ||
                File.Exists(Path.Combine(current, ".gitmodules")))
            {
                return current;
            }
            string? parent = Path.GetDirectoryName(current);
            if (parent == current) break;
            current = parent ?? "";
        }
        return Directory.GetCurrentDirectory();
    }

    private static Dictionary<string, string> LoadFolderAliases(string moduleRoot)
    {
        var aliases = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        string namingPath = Path.Combine(moduleRoot, "reversing", "docs", "reference", "naming.json");
        if (!File.Exists(namingPath)) return aliases;

        try
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(namingPath));
            if (doc.RootElement.TryGetProperty("folders", out var folders))
            {
                foreach (var item in folders.EnumerateArray())
                {
                    string scope = item.TryGetProperty("scope", out var s) ? s.GetString() ?? "" : "";
                    string orig = item.TryGetProperty("original", out var o) ? o.GetString() ?? "" : "";
                    string ext = item.TryGetProperty("extracted", out var e) ? e.GetString() ?? "" : "";
                    if (scope == "PS3 EU baseline mapping" && !string.IsNullOrEmpty(orig) && !string.IsNullOrEmpty(ext))
                    {
                        aliases[orig.ToLowerInvariant()] = ext;
                    }
                }
            }
        }
        catch { }
        return aliases;
    }

    private static string FormatRootPath(string dirPath, string moduleRoot)
    {
        try
        {
            string normDir = Path.GetFullPath(dirPath);
            string normMod = Path.GetFullPath(moduleRoot);
            if (normDir.StartsWith(normMod, StringComparison.OrdinalIgnoreCase) && normDir.Length > normMod.Length)
            {
                return Path.GetRelativePath(normMod, normDir);
            }
        }
        catch { }
        return dirPath;
    }

    // --- Connections Server ---

    private void UpdateServerStatus()
    {
        if (_server.IsRunning)
        {
            BtnToggleServer.Content = "Stop connections server";
            BtnOpenConnections.IsEnabled = true;
            LblServerStatus.Text = $"Running at {_server.Url}";
            LblServerStatus.Foreground = Avalonia.Media.Brushes.LightGreen;
        }
        else
        {
            BtnToggleServer.Content = "Start connections server";
            BtnOpenConnections.IsEnabled = false;
            LblServerStatus.Text = "Stopped";
            LblServerStatus.Foreground = Avalonia.Media.Brushes.Gray;
        }
    }

    private void OnToggleServerClick(object? sender, RoutedEventArgs e)
    {
        if (_server.IsRunning)
        {
            _server.Stop();
            UpdateServerStatus();
            return;
        }

        string db = _state.ServerDatabase;
        string webRoot = Path.Combine(_moduleRoot, "reversing", "fileviewer", "connection_explorer", "web");
        string docsRoot = Path.Combine(_moduleRoot, "reversing", "docs");

        if (!File.Exists(db))
        {
            LblServerStatus.Text = "Starting / indexing...";
            LblServerStatus.Foreground = Avalonia.Media.Brushes.Orange;
            BtnToggleServer.Content = "Indexing in progress...";
            BtnToggleServer.IsEnabled = false;

            Task.Run(() =>
            {
                try
                {
                    var indexer = new ConnectionIndexer(db, _state.ServerSource, _state.ServerExtracted);
                    indexer.Build(msg => Dispatcher.UIThread.Post(() => LblServerStatus.Text = msg));

                    Dispatcher.UIThread.Post(() =>
                    {
                        BtnToggleServer.IsEnabled = true;
                        _server.Start(db, webRoot, docsRoot, _state.ServerPort);
                        UpdateServerStatus();
                    });
                }
                catch (Exception ex)
                {
                    Dispatcher.UIThread.Post(() =>
                    {
                        BtnToggleServer.IsEnabled = true;
                        LblServerStatus.Text = $"Indexing failed: {ex.Message}";
                        LblServerStatus.Foreground = Avalonia.Media.Brushes.IndianRed;
                        UpdateServerStatus();
                    });
                }
            });
            return;
        }

        _server.Start(db, webRoot, docsRoot, _state.ServerPort);
        UpdateServerStatus();
    }

    private void OnOpenConnectionsClick(object? sender, RoutedEventArgs e)
    {
        _server.OpenBrowser();
    }

    private async void OnConfigureServerClick(object? sender, RoutedEventArgs e)
    {
        var dlg = new SettingsWindow(_state, _moduleRoot);
        await dlg.ShowDialog(this);
    }

    // --- Menu File Actions ---

    private async void OnOpenFilesClick(object? sender, RoutedEventArgs e)
    {
        var files = await StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
        {
            Title = "Open Game Files or Archives",
            AllowMultiple = true
        });

        foreach (var file in files)
        {
            LoadSingleFile(file.Path.LocalPath);
        }
    }

    private async void OnOpenFolderClick(object? sender, RoutedEventArgs e)
    {
        var folders = await StorageProvider.OpenFolderPickerAsync(new FolderPickerOpenOptions
        {
            Title = "Open Game Folder",
            AllowMultiple = false
        });

        if (folders.Count > 0)
        {
            OpenDirectory(folders[0].Path.LocalPath);
        }
    }

    private void OnClearListClick(object? sender, RoutedEventArgs e)
    {
        _rootNodes.Clear();
        _allFiles.Clear();
        _strCount = 0;
        _selectedItem = null;
        _selectedBytes = null;
        _currentResource = null;
        _currentMediaOutputs = null;

        LblItemInfo.Text = "Select an item to view details.";
        LblTreeStatus.Text = "Open a folder to list files.";
        ResetViewers();
        RenderAsciiTree();
    }

    private void OnExitClick(object? sender, RoutedEventArgs e)
    {
        _server.Stop();
        Close();
    }

    // --- Directory & File Discovery ---

    public void OpenDirectory(string dirPath)
    {
        OnClearListClick(null, new RoutedEventArgs());

        _state.LastOpenedFolder = dirPath;
        _state.Save(_moduleRoot);

        LblTreeStatus.Text = $"Scanning: {Path.GetFileName(dirPath)}...";

        string displayPath = FormatRootPath(dirPath, _moduleRoot);
        var rootNode = new FileTreeItem
        {
            Name = displayPath,
            FullPath = dirPath,
            IsDirectory = true,
            IsOpen = true,
            IsLoaded = true,
            ColorTag = "tree_default"
        };
        _rootNodes.Add(rootNode);

        ScanDirectoryFast(dirPath, rootNode, isRoot: true);

        LblTreeStatus.Text = $"Listed {_allFiles.Count:N0} files ({_strCount:N0} STR archives). Audio streams load when selected.";
        RenderAsciiTree();

        ScheduleClassification();
    }

    public void LoadSingleFile(string filePath)
    {
        var item = CreateFileItem(filePath, null);
        _rootNodes.Add(item);
        _allFiles.Add(item);
        RenderAsciiTree();
        ScheduleClassification();
    }

    private void ScanDirectoryFast(string dirPath, FileTreeItem parentNode, bool isRoot)
    {
        try
        {
            var dirInfo = new DirectoryInfo(dirPath);

            // Subdirectories
            var subDirs = dirInfo.GetDirectories()
                .Where(d => !SkipFolders.Contains(d.Name))
                .OrderBy(d => d.Name, StringComparer.OrdinalIgnoreCase);

            foreach (var d in subDirs)
            {
                string rawName = d.Name;
                string displayName = rawName;
                if (isRoot && _folderAliases.TryGetValue(rawName, out var alias))
                {
                    displayName = alias;
                }

                bool isDeferred = DeferredFolders.Contains(rawName) || DeferredFolders.Contains(displayName);

                var dNode = new FileTreeItem
                {
                    Name = displayName,
                    FullPath = d.FullName,
                    IsDirectory = true,
                    IsOpen = false,
                    IsDeferred = false,
                    Parent = parentNode,
                    ColorTag = "tree_default"
                };

                parentNode.Children.Add(dNode);

                if (isDeferred)
                {
                    // 1. Immediately scan all files located directly in audiostreams (all .mus files!)
                    try
                    {
                        var audioFiles = d.GetFiles().OrderBy(f => f.Name, StringComparer.OrdinalIgnoreCase);
                        foreach (var af in audioFiles)
                        {
                            string aExt = af.Extension.ToLowerInvariant();
                            if (SupportedSuffixes.Contains(aExt))
                            {
                                var fNode = CreateFileItem(af.FullName, dNode);
                                dNode.Children.Add(fNode);
                                _allFiles.Add(fNode);
                                if (fNode.IsArchive) _strCount++;
                            }
                        }
                    }
                    catch { }

                    // 2. Add deferred node for the deep .exa.snu stream subdirectories
                    var streamsNode = new FileTreeItem
                    {
                        Name = "**/*.exa.snu (Click to load audio streams)",
                        FullPath = d.FullName,
                        IsDirectory = true,
                        IsOpen = false,
                        IsDeferred = true,
                        Parent = dNode,
                        ColorTag = "tree_default"
                    };
                    streamsNode.Children.Add(new FileTreeItem
                    {
                        Name = "Click to load audio streams",
                        ColorTag = "unknown",
                        Parent = streamsNode
                    });
                    dNode.Children.Add(streamsNode);
                }
                else
                {
                    ScanDirectoryFast(d.FullName, dNode, isRoot: false);
                }
            }

            // Files in current directory
            var files = dirInfo.GetFiles()
                .OrderBy(f => f.Name, StringComparer.OrdinalIgnoreCase);

            foreach (var f in files)
            {
                string ext = f.Extension.ToLowerInvariant();
                string nameLower = f.Name.ToLowerInvariant();

                bool isSupported = SupportedSuffixes.Contains(ext) ||
                                   nameLower == "lighttoc" ||
                                   nameLower == "streamsetconfig";

                if (isSupported)
                {
                    var fNode = CreateFileItem(f.FullName, parentNode);
                    parentNode.Children.Add(fNode);
                    _allFiles.Add(fNode);
                    if (fNode.IsArchive) _strCount++;
                }
            }
        }
        catch (Exception ex)
        {
            parentNode.Children.Add(new FileTreeItem
            {
                Name = $"Scan error: {ex.Message}",
                ColorTag = "empty",
                Parent = parentNode
            });
        }
    }

    private FileTreeItem CreateFileItem(string filePath, FileTreeItem? parent)
    {
        string ext = Path.GetExtension(filePath).ToLowerInvariant();
        long size = 0;
        try { size = new FileInfo(filePath).Length; } catch { }

        bool isArchive = ext == ".str";

        var item = new FileTreeItem
        {
            Name = Path.GetFileName(filePath),
            FullPath = filePath,
            IsFile = true,
            IsArchive = isArchive,
            FileSize = size,
            ColorTag = size == 0 ? "empty" : "unknown",
            Parent = parent
        };

        if (isArchive)
        {
            item.Children.Add(new FileTreeItem
            {
                Name = "Expand to load archive",
                ColorTag = "unknown",
                Parent = item
            });
        }
        else
        {
            item.Children.Add(new FileTreeItem
            {
                Name = "Select to view",
                ColorTag = "unknown",
                Parent = item
            });
        }

        return item;
    }

    private void EnsureFolderListed(FileTreeItem node)
    {
        if (!node.IsDeferred) return;
        node.IsDeferred = false;
        node.Children.Clear();
        node.IsOpen = true;
        LblTreeStatus.Text = $"Scanning audio folder: {node.Name}...";

        Task.Run(() =>
        {
            if (node.Name.Contains("**/*.exa.snu"))
            {
                try
                {
                    var dirInfo = new DirectoryInfo(node.FullPath);
                    var subDirs = dirInfo.GetDirectories()
                        .Where(d => !SkipFolders.Contains(d.Name))
                        .OrderBy(d => d.Name, StringComparer.OrdinalIgnoreCase);

                    foreach (var d in subDirs)
                    {
                        var dNode = new FileTreeItem
                        {
                            Name = d.Name,
                            FullPath = d.FullName,
                            IsDirectory = true,
                            IsOpen = false,
                            Parent = node,
                            ColorTag = "tree_default"
                        };
                        node.Children.Add(dNode);
                        ScanDirectoryFast(d.FullName, dNode, isRoot: false);
                    }
                }
                catch { }
            }
            else
            {
                ScanDirectoryFast(node.FullPath, node, isRoot: false);
            }

            Dispatcher.UIThread.Post(() =>
            {
                RenderAsciiTree();
                LblTreeStatus.Text = $"Listed audio files in {node.Name}.";
                ScheduleClassification();
            });
        });
    }

    private void ToggleArchiveNode(FileTreeItem node)
    {
        if (!node.IsLoaded)
        {
            node.IsLoaded = true;
            LblTreeStatus.Text = $"Loading archive: {node.Name}...";

            Task.Run(() =>
            {
                try
                {
                    var archive = StrArchive.Load(node.FullPath);
                    Dispatcher.UIThread.Post(() =>
                    {
                        PopulateStrArchive(node, archive);
                        node.IsOpen = true;
                        LblTreeStatus.Text = $"Loaded {node.Name} ({archive.Sections.Count} sections)";
                        RenderAsciiTree();
                    });
                }
                catch (Exception ex)
                {
                    Dispatcher.UIThread.Post(() =>
                    {
                        node.Children.Clear();
                        node.Children.Add(new FileTreeItem
                        {
                            Name = $"Error loading archive: {ex.Message}",
                            ColorTag = "empty",
                            Parent = node
                        });
                        node.IsOpen = true;
                        RenderAsciiTree();
                    });
                }
            });
        }
        else
        {
            node.IsOpen = !node.IsOpen;
            RenderAsciiTree();
        }
    }

    private void PopulateStrArchive(FileTreeItem node, StrArchive archive)
    {
        node.Children.Clear();

        for (int sIdx = 0; sIdx < archive.Sections.Count; sIdx++)
        {
            var sec = archive.Sections[sIdx];
            var secItem = new FileTreeItem
            {
                Name = $"Section {sIdx} ({sec.Chunks.Count} chunks, {sec.Descriptor.DataSize / 1024} KiB)",
                IsLoaded = true,
                IsOpen = true,
                ColorTag = "tree_default",
                Parent = node
            };

            foreach (var chunk in sec.Chunks)
            {
                string chunkName = !string.IsNullOrEmpty(chunk.FileName) ? chunk.FileName :
                                  (!string.IsNullOrEmpty(chunk.FullPath) ? Path.GetFileName(chunk.FullPath) : chunk.TypeName);

                string colorTag = "asset_unknown";
                if (chunk.PayloadData.Length > 0)
                {
                    string kind = FormatDetector.Identify(chunk.FullPath ?? chunk.FileName, chunk.ResourceType, chunk.PayloadData);
                    if (kind == ".lh2" || kind == ".dat.uie" || kind == ".dat.simgroup" ||
                        kind == ".txt" || kind == ".txd" || kind == ".lighttoc" || kind == ".shk.ps3")
                    {
                        colorTag = "asset_supported";
                    }
                    else if (!string.IsNullOrEmpty(kind))
                    {
                        colorTag = "asset_partial";
                    }
                    else
                    {
                        colorTag = "asset_hex_only";
                    }
                }

                var cItem = new FileTreeItem
                {
                    Name = $"{chunkName} [{chunk.ResourceType}] ({chunk.PayloadSize} B)",
                    FullPath = chunk.FullPath ?? string.Empty,
                    IsAsset = true,
                    Chunk = chunk,
                    PayloadData = chunk.PayloadData,
                    FileSize = chunk.PayloadSize,
                    ColorTag = colorTag,
                    Parent = secItem
                };

                secItem.Children.Add(cItem);
            }

            node.Children.Add(secItem);
        }
    }

    // --- Classification (Duplicates, Unique, Empty) ---

    private void ScheduleClassification()
    {
        var items = _allFiles.ToList();
        if (items.Count == 0) return;

        Task.Run(() =>
        {
            var bySize = new Dictionary<long, List<FileTreeItem>>();

            foreach (var item in items)
            {
                if (item.FileSize == 0)
                {
                    item.ColorTag = "empty";
                    continue;
                }

                // Check for empty SToc
                if (item.IsArchive && item.FileSize >= 12)
                {
                    try
                    {
                        using var fs = new FileStream(item.FullPath, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
                        byte[] hdr = new byte[12];
                        int r = fs.Read(hdr, 0, 12);
                        if (r >= 9 && hdr[0] == 'S' && hdr[1] == 'T' && hdr[2] == 'o' && hdr[3] == 'c' && hdr[8] == 0)
                        {
                            item.ColorTag = "empty";
                            continue;
                        }
                    }
                    catch { }
                }

                if (!bySize.TryGetValue(item.FileSize, out var list))
                {
                    list = new List<FileTreeItem>();
                    bySize[item.FileSize] = list;
                }
                list.Add(item);
            }

            foreach (var (size, list) in bySize)
            {
                if (list.Count == 1)
                {
                    list[0].ColorTag = "unique";
                }
                else
                {
                    var byHash = new Dictionary<string, List<FileTreeItem>>(StringComparer.OrdinalIgnoreCase);

                    foreach (var item in list)
                    {
                        try
                        {
                            using var fs = new FileStream(item.FullPath, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
                            byte[] hashBytes = SHA256.HashData(fs);
                            string sha = Convert.ToHexString(hashBytes).ToLowerInvariant();

                            if (!byHash.TryGetValue(sha, out var hashList))
                            {
                                hashList = new List<FileTreeItem>();
                                byHash[sha] = hashList;
                            }
                            hashList.Add(item);
                        }
                        catch
                        {
                            item.ColorTag = "unknown";
                        }
                    }

                    foreach (var (_, hashList) in byHash)
                    {
                        string tag = hashList.Count > 1 ? "duplicate" : "unique";
                        foreach (var item in hashList)
                        {
                            item.ColorTag = tag;
                        }
                    }
                }
            }

            Dispatcher.UIThread.Post(RenderAsciiTree);
        });
    }

    // --- ASCII Tree Rendering ---

    private void RenderAsciiTree()
    {
        var rows = AsciiTreeGenerator.GenerateRows(_rootNodes, _filterPattern);
        TreeListBox.ItemsSource = rows;

        if (_selectedItem != null)
        {
            var selectedRow = rows.FirstOrDefault(r => r.Node == _selectedItem);
            if (selectedRow != null)
            {
                TreeListBox.SelectedItem = selectedRow;
            }
        }
    }

    // --- Tree Interactions ---

    private void OnTreeSelectionChanged(object? sender, SelectionChangedEventArgs e)
    {
        if (TreeListBox.SelectedItem is AsciiTreeRow row && row.Node != null)
        {
            _selectedItem = row.Node;
            SelectNode(row.Node);
        }
    }

    private void OnTreePointerPressed(object? sender, PointerPressedEventArgs e)
    {
        var source = e.Source as Visual;
        while (source != null && source is not ListBoxItem && source != TreeListBox)
        {
            source = source.GetVisualParent();
        }

        if (source is ListBoxItem listItem && listItem.DataContext is AsciiTreeRow row && row.Node != null)
        {
            var node = row.Node;
            bool alreadySelected = _selectedItem == node;
            _selectedItem = node;
            SelectNode(node);

            if (node.IsDirectory)
            {
                if (node.IsDeferred)
                {
                    EnsureFolderListed(node);
                }
                else
                {
                    node.IsOpen = !node.IsOpen;
                    RenderAsciiTree();
                }
            }
            else if (node.IsFile && node.IsArchive && alreadySelected)
            {
                ToggleArchiveNode(node);
            }
            else if (!node.IsFile && !node.IsDirectory && node.Children.Count > 0)
            {
                node.IsOpen = !node.IsOpen;
                RenderAsciiTree();
            }
        }
    }

    private void OnTreeDoubleTapped(object? sender, TappedEventArgs e)
    {
        var source = e.Source as Visual;
        while (source != null && source is not ListBoxItem && source != TreeListBox)
        {
            source = source.GetVisualParent();
        }

        if (source is ListBoxItem listItem && listItem.DataContext is AsciiTreeRow row && row.Node != null)
        {
            var node = row.Node;
            if (node.IsFile && node.IsArchive)
            {
                if (!node.IsOpen)
                {
                    ToggleArchiveNode(node);
                }
            }
            else if (node.IsDirectory)
            {
                if (node.IsDeferred)
                {
                    EnsureFolderListed(node);
                }
                else
                {
                    node.IsOpen = !node.IsOpen;
                    RenderAsciiTree();
                }
            }
        }
    }

    private void OnTreeKeyDown(object? sender, KeyEventArgs e)
    {
        if (TreeListBox.SelectedItem is not AsciiTreeRow row || row.Node == null) return;
        var node = row.Node;

        if (e.Key == Key.Right || e.Key == Key.Enter)
        {
            if (node.IsDirectory)
            {
                if (node.IsDeferred) EnsureFolderListed(node);
                else if (!node.IsOpen) { node.IsOpen = true; RenderAsciiTree(); }
                e.Handled = true;
            }
            else if (node.IsFile && node.IsArchive)
            {
                if (!node.IsOpen) ToggleArchiveNode(node);
                e.Handled = true;
            }
            else if (node.Children.Count > 0 && !node.IsOpen)
            {
                node.IsOpen = true;
                RenderAsciiTree();
                e.Handled = true;
            }
        }
        else if (e.Key == Key.Left)
        {
            if (node.IsOpen)
            {
                node.IsOpen = false;
                RenderAsciiTree();
                e.Handled = true;
            }
            else if (node.Parent != null)
            {
                _selectedItem = node.Parent;
                RenderAsciiTree();
                e.Handled = true;
            }
        }
    }

    private void OnExpandAllClick(object? sender, RoutedEventArgs e)
    {
        void ExpandRecursive(FileTreeItem node)
        {
            if (node.IsDirectory && !node.IsDeferred)
            {
                node.IsOpen = true;
                foreach (var child in node.Children)
                {
                    ExpandRecursive(child);
                }
            }
        }

        foreach (var r in _rootNodes)
        {
            ExpandRecursive(r);
        }
        RenderAsciiTree();
    }

    private void OnCollapseAllClick(object? sender, RoutedEventArgs e)
    {
        void CollapseRecursive(FileTreeItem node)
        {
            if (node.IsDirectory)
            {
                // Collapse subdirectories (keep root folder open)
                if (node.Parent != null)
                {
                    node.IsOpen = false;
                }
                foreach (var child in node.Children)
                {
                    CollapseRecursive(child);
                }
            }
            else if (node.IsArchive)
            {
                node.IsOpen = false;
            }
        }

        foreach (var r in _rootNodes)
        {
            CollapseRecursive(r);
        }
        RenderAsciiTree();
    }

    private void OnSearchTextChanged(object? sender, TextChangedEventArgs e)
    {
        _filterPattern = TxtSearch.Text ?? "";
        RenderAsciiTree();
    }

    // --- Details & Viewers ---

    private void SelectNode(FileTreeItem node)
    {
        ResetViewers();

        if (node.IsDirectory)
        {
            LblItemInfo.Text = $"{node.Name} (Directory)";
            TxtContentViewer.Text = $"Directory: {node.FullPath}\nContains: {node.Children.Count} items";
            TxtContentViewer.IsVisible = true;
            return;
        }

        byte[]? data = node.PayloadData;
        if (data == null && node.IsFile && File.Exists(node.FullPath))
        {
            try
            {
                var fi = new FileInfo(node.FullPath);
                if (fi.Length < 32 * 1024 * 1024)
                {
                    data = File.ReadAllBytes(node.FullPath);
                }
            }
            catch { }
        }

        _selectedBytes = data;
        _hexOffset = 0;

        string name = node.Name;
        long size = node.FileSize;
        string resType = node.Chunk?.ResourceType ?? "";

        LblItemInfo.Text = string.IsNullOrEmpty(resType)
            ? $"{name} ({size:N0} bytes)"
            : $"{name} [{resType}] ({size:N0} bytes)";

        BtnExtractPayload.IsEnabled = data != null;

        // View mode: default to interpretation view
        if (_viewMode == "hex")
        {
            ShowHexView();
        }
        else
        {
            ShowInterpretationView(node, data);
        }
    }

    private void ShowInterpretationView(FileTreeItem node, byte[]? data)
    {
        string name = node.Name;
        string resType = node.Chunk?.ResourceType ?? "";
        string ext = Path.GetExtension(name).ToLowerInvariant();

        BtnToggleViewMode.IsEnabled = true;
        BtnToggleViewMode.Content = "View raw HEX";

        bool isAudio = ext is ".snu" or ".snr" or ".mus" or ".sbk" or ".wav" or ".ogg" or ".mp3" or ".flac";
        bool isVideo = ext is ".vp6" or ".mp4" or ".ogv" or ".avi" or ".webm";

        // 1. Audio and Video media files: show player button and AudioMap metadata
        if (isAudio || isVideo)
        {
            BtnPlayMedia.IsVisible = true;
            BtnPlayMedia.Content = isVideo ? "Watch" : "Play";
            BtnOpenExternal.IsVisible = true;
            BtnOpenExternal.Content = isVideo ? "Open Video Player" : "Open Audio Player";

            string desc = AudioMapRegistry.Instance.FormatDescription(node.FullPath, name, node.FileSize);

            if (ext == ".mus" && data != null && data.Length >= 40)
            {
                var segments = MediaConverter.ExtractMusSegments(data);
                var sbMus = new StringBuilder(desc);
                sbMus.AppendLine($"Extracted Music Segments: {segments.Count}");
                for (int i = 0; i < segments.Count; i++)
                {
                    sbMus.AppendLine($"  - Segment {segments[i].Index:D3}: SNR={segments[i].Snr.Length:N0} bytes, SNS={segments[i].Sns.Length:N0} bytes");
                }
                desc = sbMus.ToString();
            }

            TxtContentViewer.Text = desc;
            TxtContentViewer.IsVisible = true;
            return;
        }

        // 2. TXD / Textures
        if (data != null && TxdParser.IsTxd(data, name, resType))
        {
            try
            {
                _currentTextures = TxdParser.ParseTextures(data);
                if (_currentTextures.Count > 0)
                {
                    LstTextures.ItemsSource = _currentTextures;
                    LstTextures.SelectedIndex = 0;
                    PanelTextureViewer.IsVisible = true;
                    BtnExportJson.IsEnabled = true;
                    BtnOpenExternal.IsVisible = true;
                    BtnOpenExternal.Content = "Export Texture";
                    return;
                }
            }
            catch { }
        }

        // 3. LH2 Localization Table
        if (data != null && (ext == ".lh2" || resType.Equals("LH2", StringComparison.OrdinalIgnoreCase) ||
            (data.Length >= 4 && data[0] == '2' && data[1] == 'H' && data[2] == 'C' && data[3] == 'L')))
        {
            try
            {
                string csv = Lh2Parser.ParseToCsv(data);
                var lines = csv.Split('\n', StringSplitOptions.RemoveEmptyEntries);
                if (lines.Length > 0)
                {
                    var headers = lines[0].Split(',');
                    var table = new System.Data.DataTable();
                    foreach (var h in headers) table.Columns.Add(h.Trim());
                    for (int li = 1; li < lines.Length; li++)
                    {
                        var parts = lines[li].Split(',');
                        if (parts.Length == headers.Length) table.Rows.Add(parts);
                    }
                    GridDataViewer.ItemsSource = table.DefaultView;
                    LblTableSummary.Text = $"LH2 Localization Table ({lines.Length - 1:N0} strings)";
                    PanelTableViewer.IsVisible = true;
                    BtnExportJson.IsEnabled = true;
                    return;
                }
            }
            catch { }
        }

        // 4. Structured Game Formats
        if (data != null)
        {
            try
            {
                var parsed = ResourceDispatcher.Parse(data, name, resType);
                _currentResource = parsed;

                if (parsed.Structure is List<TreeNodeModel> treeList && treeList.Count > 0)
                {
                    TreeContentViewer.ItemsSource = treeList;
                    TreeContentViewer.IsVisible = true;
                    BtnExportJson.IsEnabled = true;
                    return;
                }

                if (parsed.Structure is Dictionary<string, object> dict && dict.Count > 0)
                {
                    var rootModel = FormatDetector.BuildTreeNode(parsed.Format, dict);
                    TreeContentViewer.ItemsSource = new List<TreeNodeModel> { rootModel };
                    TreeContentViewer.IsVisible = true;
                    BtnExportJson.IsEnabled = true;
                    return;
                }

                if (parsed.Structure is string textContent && !string.IsNullOrEmpty(textContent))
                {
                    TxtContentViewer.Text = textContent;
                    TxtContentViewer.IsVisible = true;
                    return;
                }
            }
            catch { }
        }

        // 5. Text / Code / Script / Config Files
        if (data != null && ext is ".txt" or ".lua" or ".tree" or ".json" or ".xml" or ".csv" or ".yaml" or ".yml" or ".toml" or ".fnt" or ".srt" or ".vtt")
        {
            try
            {
                TxtContentViewer.Text = Encoding.UTF8.GetString(data);
                TxtContentViewer.IsVisible = true;
                BtnOpenExternal.IsVisible = true;
                BtnOpenExternal.Content = "Open in Editor";
                return;
            }
            catch { }
        }

        // 6. 3D Model files (.blend, .glb)
        if (ext is ".blend" or ".glb")
        {
            BtnOpenExternal.IsVisible = true;
            BtnOpenExternal.Content = ext == ".blend" ? "Open in Blender" : "Open 3D Viewer";
            TxtContentViewer.Text = $"3D Model: {name}\nSize: {node.FileSize:N0} bytes\nPath: {node.FullPath}\n\nClick '{BtnOpenExternal.Content}' to launch in viewer.";
            TxtContentViewer.IsVisible = true;
            return;
        }

        // 7. General format interpretation / doc notes
        string identifiedFormat = data != null ? FormatDetector.Identify(name, resType, data) : "";
        var sb = new StringBuilder();
        sb.AppendLine($"File: {name}");
        sb.AppendLine($"Size: {node.FileSize:N0} bytes");
        if (!string.IsNullOrEmpty(resType)) sb.AppendLine($"Resource Type: {resType}");
        if (!string.IsNullOrEmpty(identifiedFormat)) sb.AppendLine($"Identified Format: {identifiedFormat}");
        sb.AppendLine();

        // Check if there is AudioMap or documented metadata
        var docMeta = AudioMapRegistry.Instance.FindMetadata(node.FullPath, name);
        if (docMeta != null)
        {
            sb.AppendLine("Documentation Metadata (reversing/docs):");
            sb.AppendLine($"  Asset ID: {docMeta.Id}");
            if (!string.IsNullOrEmpty(docMeta.AudioType)) sb.AppendLine($"  Type: {docMeta.AudioType}");
            if (!string.IsNullOrEmpty(docMeta.SpeakerName)) sb.AppendLine($"  Speaker: {docMeta.SpeakerName}");
            if (docMeta.Locations.Count > 0) sb.AppendLine($"  Locations: {string.Join(", ", docMeta.Locations)}");
            if (!string.IsNullOrEmpty(docMeta.Notes)) sb.AppendLine($"  Notes: {docMeta.Notes}");
            sb.AppendLine();
        }

        sb.AppendLine("Click 'View raw HEX' above to inspect hexadecimal byte dump.");
        TxtContentViewer.Text = sb.ToString();
        TxtContentViewer.IsVisible = true;
    }

    private void ShowHexView()
    {
        BtnToggleViewMode.IsEnabled = _selectedBytes != null;
        BtnToggleViewMode.Content = "View interpretation";

        PanelHexPager.IsVisible = _selectedBytes != null && _selectedBytes.Length > HexPageSize;
        LblHexOffset.Text = $"0x{_hexOffset:X4}";

        if (_selectedBytes != null && _selectedBytes.Length > 0)
        {
            TxtContentViewer.Text = HexDump.FormatPage(_selectedBytes, _hexOffset, HexPageSize);
        }
        else
        {
            TxtContentViewer.Text = "<No payload data available>";
        }

        TxtContentViewer.IsVisible = true;
    }

    private void OnToggleViewModeClick(object? sender, RoutedEventArgs e)
    {
        _viewMode = (_viewMode == "hex") ? "interpretation" : "hex";

        if (_selectedItem != null)
        {
            if (_viewMode == "hex")
            {
                ShowHexView();
            }
            else
            {
                ResetViewers();
                ShowInterpretationView(_selectedItem, _selectedBytes);
            }
        }
    }

    private void OnHexPrevClick(object? sender, RoutedEventArgs e)
    {
        if (_hexOffset >= HexPageSize)
        {
            _hexOffset -= HexPageSize;
            ShowHexView();
        }
    }

    private void OnHexNextClick(object? sender, RoutedEventArgs e)
    {
        if (_selectedBytes != null && _hexOffset + HexPageSize < _selectedBytes.Length)
        {
            _hexOffset += HexPageSize;
            ShowHexView();
        }
    }

    private void OnTextureSelectionChanged(object? sender, SelectionChangedEventArgs e)
    {
        if (LstTextures.SelectedItem is TextureImageInfo tex)
        {
            LblTextureInfo.Text = $"{tex.Name} ({tex.Width}x{tex.Height}, {tex.FormatName})";
            try
            {
                var wb = new WriteableBitmap(
                    new PixelSize(tex.Width, tex.Height),
                    new Vector(96, 96),
                    Avalonia.Platform.PixelFormat.Bgra8888,
                    Avalonia.Platform.AlphaFormat.Premul);

                using (var fb = wb.Lock())
                {
                    System.Runtime.InteropServices.Marshal.Copy(tex.RgbaPixels, 0, fb.Address, Math.Min(tex.RgbaPixels.Length, fb.RowBytes * tex.Height));
                }

                ImgTexturePreview.Source = wb;
            }
            catch (Exception ex)
            {
                LblTextureInfo.Text += $" [Error rendering: {ex.Message}]";
            }
        }
    }

    private async void OnPlayMediaClick(object? sender, RoutedEventArgs e)
    {
        if (_selectedItem == null) return;
        var node = _selectedItem;

        BtnPlayMedia.IsEnabled = false;
        string originalContent = BtnPlayMedia.Content?.ToString() ?? "Play";
        BtnPlayMedia.Content = "Converting...";
        LblGlobalStatus.Text = $"Preparing preview for {node.Name}...";

        try
        {
            var outputs = await Task.Run(() => MediaConverter.Instance.ConvertAsync(
                node.FullPath,
                _selectedBytes,
                node.Name,
                _moduleRoot));

            if (outputs.Count > 0)
            {
                _currentMediaOutputs = outputs;

                if (outputs.Count > 1)
                {
                    CmbMediaTrack.ItemsSource = outputs.Select(Path.GetFileName).ToList();
                    CmbMediaTrack.SelectedIndex = 0;
                    CmbMediaTrack.IsVisible = true;
                }
                else
                {
                    CmbMediaTrack.IsVisible = false;
                }

                string target = outputs[0];
                MediaConverter.Instance.OpenDefault(target);
                LblGlobalStatus.Text = $"Playing: {Path.GetFileName(target)}";
            }
            else
            {
                LblGlobalStatus.Text = $"No playable preview produced for {node.Name}";
            }
        }
        catch (Exception ex)
        {
            LblGlobalStatus.Text = $"Conversion error: {ex.Message}";
        }
        finally
        {
            BtnPlayMedia.IsEnabled = true;
            BtnPlayMedia.Content = originalContent;
        }
    }

    private void OnMediaTrackSelectionChanged(object? sender, SelectionChangedEventArgs e)
    {
        if (CmbMediaTrack.SelectedIndex >= 0 && _currentMediaOutputs != null &&
            CmbMediaTrack.SelectedIndex < _currentMediaOutputs.Count)
        {
            string target = _currentMediaOutputs[CmbMediaTrack.SelectedIndex];
            MediaConverter.Instance.OpenDefault(target);
            LblGlobalStatus.Text = $"Playing: {Path.GetFileName(target)}";
        }
    }

    private void OnOpenExternalClick(object? sender, RoutedEventArgs e)
    {
        if (_selectedItem == null) return;
        string path = _selectedItem.FullPath;
        string ext = Path.GetExtension(path).ToLowerInvariant();

        if (ext == ".blend")
        {
            string? blender = MediaConverter.FindTool("blender", _moduleRoot);
            if (blender != null && File.Exists(path))
            {
                try
                {
                    Process.Start(new ProcessStartInfo { FileName = blender, Arguments = $"\"{path}\"", UseShellExecute = false });
                    LblGlobalStatus.Text = $"Opened {Path.GetFileName(path)} in Blender";
                    return;
                }
                catch { }
            }
        }

        if (ext is ".vp6" or ".snu" or ".mus" or ".sbk" or ".snr")
        {
            OnPlayMediaClick(sender, e);
            return;
        }

        if (File.Exists(path))
        {
            try
            {
                Process.Start(new ProcessStartInfo { FileName = path, UseShellExecute = true });
                LblGlobalStatus.Text = $"Opened: {Path.GetFileName(path)}";
            }
            catch (Exception ex)
            {
                LblGlobalStatus.Text = $"Error opening {path}: {ex.Message}";
            }
        }
    }

    private async void OnExtractPayloadClick(object? sender, RoutedEventArgs e)
    {
        if (_selectedBytes == null || _selectedItem == null) return;

        var file = await StorageProvider.SaveFilePickerAsync(new FilePickerSaveOptions
        {
            Title = "Extract Asset Payload",
            SuggestedFileName = _selectedItem.Name
        });

        if (file != null)
        {
            await File.WriteAllBytesAsync(file.Path.LocalPath, _selectedBytes);
            LblGlobalStatus.Text = $"Extracted {_selectedBytes.Length:N0} bytes to {file.Name}";
        }
    }

    private async void OnExportJsonClick(object? sender, RoutedEventArgs e)
    {
        if (_currentResource == null || _selectedItem == null) return;

        var file = await StorageProvider.SaveFilePickerAsync(new FilePickerSaveOptions
        {
            Title = "Export Resource Structure to JSON",
            DefaultExtension = "json",
            SuggestedFileName = $"{_selectedItem.Name}.json"
        });

        if (file != null)
        {
            string json = JsonSerializer.Serialize(_currentResource, new JsonSerializerOptions { WriteIndented = true });
            await File.WriteAllTextAsync(file.Path.LocalPath, json);
            LblGlobalStatus.Text = $"Exported JSON to {file.Name}";
        }
    }

    private void ResetViewers()
    {
        TxtContentViewer.IsVisible = false;
        PanelTableViewer.IsVisible = false;
        PanelTextureViewer.IsVisible = false;
        TreeContentViewer.IsVisible = false;
        PanelHexPager.IsVisible = false;

        BtnExtractPayload.IsEnabled = false;
        BtnExportJson.IsEnabled = false;
        BtnToggleViewMode.IsEnabled = false;
        BtnPlayMedia.IsVisible = false;
        BtnOpenExternal.IsVisible = false;
        CmbMediaTrack.IsVisible = false;

        _currentResource = null;
        _currentTextures.Clear();
    }
}
