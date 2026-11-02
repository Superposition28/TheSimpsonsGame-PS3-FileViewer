using System.Text.Json;

namespace TheSimpsonsGame.FileViewer.State;

public class ViewerState
{
    public int ServerPort { get; set; } = 8781;
    public string ServerSource { get; set; } = string.Empty;
    public string ServerDatabase { get; set; } = string.Empty;
    public List<string> ServerExtracted { get; set; } = new();
    public string LastOpenedFolder { get; set; } = string.Empty;

    public static ViewerState Load(string moduleRoot)
    {
        var state = new ViewerState
        {
            ServerSource = Path.Combine(moduleRoot, "Source", "PS3", "EU", "1", "PS3_GAME", "USRDIR"),
            ServerDatabase = Path.Combine(moduleRoot, "GameFiles", "file-connections", "index.sqlite"),
            ServerExtracted = new List<string>
            {
                Path.Combine(moduleRoot, "GameFiles", "PS3-EU-Full-audio_reorg-isRenamed"),
                Path.Combine(moduleRoot, "GameFiles", "PS3-EU-FullFlattened-audio_reorg-isRenamed")
            }
        };

        string jsonPath = Path.Combine(moduleRoot, "reversing", "fileviewer", "fileviewer_state.json");
        if (File.Exists(jsonPath))
        {
            try
            {
                string text = File.ReadAllText(jsonPath);
                var loaded = JsonSerializer.Deserialize<ViewerState>(text);
                if (loaded != null)
                {
                    if (loaded.ServerPort > 0) state.ServerPort = loaded.ServerPort;
                    if (!string.IsNullOrEmpty(loaded.ServerSource)) state.ServerSource = loaded.ServerSource;
                    if (!string.IsNullOrEmpty(loaded.ServerDatabase)) state.ServerDatabase = loaded.ServerDatabase;
                    if (loaded.ServerExtracted?.Count > 0) state.ServerExtracted = loaded.ServerExtracted;
                    if (!string.IsNullOrEmpty(loaded.LastOpenedFolder)) state.LastOpenedFolder = loaded.LastOpenedFolder;
                }
            }
            catch { }
        }

        return state;
    }

    public void Save(string moduleRoot)
    {
        try
        {
            string jsonPath = Path.Combine(moduleRoot, "reversing", "fileviewer", "fileviewer_state.json");
            string text = JsonSerializer.Serialize(this, new JsonSerializerOptions { WriteIndented = true });
            File.WriteAllText(jsonPath, text);
        }
        catch { }
    }
}

