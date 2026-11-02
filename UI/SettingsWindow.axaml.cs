using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Platform.Storage;
using TheSimpsonsGame.FileViewer.Connections;
using TheSimpsonsGame.FileViewer.State;

namespace TheSimpsonsGame.FileViewer.UI;

public partial class SettingsWindow : Window
{
    private readonly ViewerState _state;
    private readonly string _moduleRoot;

    public SettingsWindow() : this(new ViewerState(), "")
    {
    }

    public SettingsWindow(ViewerState state, string moduleRoot)
    {
        InitializeComponent();
        _state = state;
        _moduleRoot = moduleRoot;

        TxtPort.Text = _state.ServerPort.ToString();
        TxtSource.Text = _state.ServerSource;
        TxtDatabase.Text = _state.ServerDatabase;
        TxtExtracted.Text = string.Join(";", _state.ServerExtracted);
    }

    private async void OnBrowseSourceClick(object? sender, RoutedEventArgs e)
    {
        var folders = await StorageProvider.OpenFolderPickerAsync(new FolderPickerOpenOptions
        {
            Title = "Select Original Source Root (USRDIR)",
            AllowMultiple = false
        });

        if (folders.Count > 0)
        {
            TxtSource.Text = folders[0].Path.LocalPath;
        }
    }

    private async void OnBrowseDatabaseClick(object? sender, RoutedEventArgs e)
    {
        var file = await StorageProvider.SaveFilePickerAsync(new FilePickerSaveOptions
        {
            Title = "Select Connections SQLite Database Path",
            DefaultExtension = "sqlite",
            SuggestedFileName = "index.sqlite"
        });

        if (file != null)
        {
            TxtDatabase.Text = file.Path.LocalPath;
        }
    }

    private async void OnRebuildClick(object? sender, RoutedEventArgs e)
    {
        BtnRebuild.IsEnabled = false;
        LblBuildStatus.Text = "Building index...";
        TxtLog.Text = $"Starting index build at {DateTime.Now}...\n";

        string dbPath = TxtDatabase.Text ?? "";
        string srcPath = TxtSource.Text ?? "";
        var extractedPaths = (TxtExtracted.Text ?? "")
            .Split(';', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .ToList();

        try
        {
            var summary = await Task.Run(() =>
            {
                var indexer = new ConnectionIndexer(dbPath, srcPath, extractedPaths);
                return indexer.Build(msg =>
                {
                    Avalonia.Threading.Dispatcher.UIThread.Post(() =>
                    {
                        TxtLog.Text += $"{msg}\n";
                    });
                });
            });

            TxtLog.Text += $"Build complete in {summary["seconds"]}s!\nTotal Files: {summary["files"]}\nTotal Identifiers: {summary["identifiers"]}\nTotal Provenance Edges: {summary["provenance_edges"]}\n";
            LblBuildStatus.Text = "Build complete!";
        }
        catch (Exception ex)
        {
            TxtLog.Text += $"Error rebuilding database: {ex.Message}\n";
            LblBuildStatus.Text = "Error!";
        }
        finally
        {
            BtnRebuild.IsEnabled = true;
        }
    }

    private void OnSaveClick(object? sender, RoutedEventArgs e)
    {
        if (int.TryParse(TxtPort.Text, out int port))
            _state.ServerPort = port;

        _state.ServerSource = TxtSource.Text ?? "";
        _state.ServerDatabase = TxtDatabase.Text ?? "";
        _state.ServerExtracted = (TxtExtracted.Text ?? "")
            .Split(';', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .ToList();

        _state.Save(_moduleRoot);
        Close(true);
    }

    private void OnCancelClick(object? sender, RoutedEventArgs e)
    {
        Close(false);
    }
}
