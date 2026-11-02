using System.Text.RegularExpressions;

namespace TheSimpsonsGame.FileViewer.Formats;

public class AudioAssetMetadata
{
    public string Id { get; set; } = string.Empty;
    public string AudioType { get; set; } = string.Empty;
    public string Scope { get; set; } = string.Empty;
    public string OriginalDirectory { get; set; } = string.Empty;
    public List<string> FilePatterns { get; } = new();
    public List<Regex> PatternRegexes { get; } = new();
    public string SpeakerId { get; set; } = string.Empty;
    public string SpeakerName { get; set; } = string.Empty;
    public string SpeakerStatus { get; set; } = string.Empty;
    public List<string> Locations { get; } = new();
    public string Notes { get; set; } = string.Empty;
    public string Category { get; set; } = string.Empty;
    public string Area { get; set; } = string.Empty;
    public string Nickname { get; set; } = string.Empty;
}

public class AudioMapRegistry
{
    private static AudioMapRegistry? _instance;
    public static AudioMapRegistry Instance => _instance ??= new AudioMapRegistry();

    private readonly Dictionary<string, (string Name, string Status)> _speakers = new(StringComparer.OrdinalIgnoreCase);
    private readonly Dictionary<string, string> _locations = new(StringComparer.OrdinalIgnoreCase);
    private readonly List<AudioAssetMetadata> _assets = new();
    private bool _loaded;
    private readonly object _lock = new();

    public bool IsLoaded => _loaded;
    public int AssetCount => _assets.Count;

    public void EnsureLoaded(string moduleRoot)
    {
        if (_loaded) return;
        lock (_lock)
        {
            if (_loaded) return;
            string yamlPath = Path.Combine(moduleRoot, "reversing", "docs", "PS3_GAME", "USRDIR", "A1_Audio", "AudioMap.yaml");
            if (File.Exists(yamlPath))
            {
                Load(yamlPath);
            }
        }
    }

    public void Load(string yamlPath)
    {
        _speakers.Clear();
        _locations.Clear();
        _assets.Clear();

        string[] lines = File.ReadAllLines(yamlPath);

        string section = "";
        string currentKey = "";
        AudioAssetMetadata? currentAsset = null;
        string subSection = "";
        string subSubSection = "";

        for (int i = 0; i < lines.Length; i++)
        {
            string line = lines[i];
            string trimmed = line.Trim();
            if (string.IsNullOrEmpty(trimmed) || trimmed.StartsWith('#')) continue;

            int indent = line.TakeWhile(char.IsWhiteSpace).Count();

            if (indent == 0)
            {
                if (trimmed.StartsWith("locations:")) { section = "locations"; continue; }
                if (trimmed.StartsWith("speakers:")) { section = "speakers"; continue; }
                if (trimmed.StartsWith("assets:")) { section = "assets"; continue; }
                if (trimmed.StartsWith("- id:"))
                {
                    section = "assets";
                    currentAsset = new AudioAssetMetadata
                    {
                        Id = trimmed[5..].Trim().Trim('\'', '"')
                    };
                    _assets.Add(currentAsset);
                    subSection = "";
                    subSubSection = "";
                    continue;
                }
                section = "";
                continue;
            }

            if (section == "speakers")
            {
                if (indent == 2 && trimmed.EndsWith(':'))
                {
                    currentKey = trimmed.TrimEnd(':');
                    _speakers[currentKey] = (currentKey, "");
                }
                else if (indent == 4 && !string.IsNullOrEmpty(currentKey))
                {
                    int colon = trimmed.IndexOf(':');
                    if (colon > 0)
                    {
                        string k = trimmed[..colon].Trim();
                        string val = trimmed[(colon + 1)..].Trim().Trim('\'', '"');
                        var existing = _speakers[currentKey];
                        if (k == "display_name")
                            _speakers[currentKey] = (val, existing.Status);
                        else if (k == "review_status")
                            _speakers[currentKey] = (existing.Name, val);
                    }
                }
            }
            else if (section == "locations")
            {
                if (indent == 4 && trimmed.EndsWith(':'))
                {
                    currentKey = trimmed.TrimEnd(':');
                }
                else if (indent == 6 && !string.IsNullOrEmpty(currentKey))
                {
                    int colon = trimmed.IndexOf(':');
                    if (colon > 0)
                    {
                        string k = trimmed[..colon].Trim();
                        string val = trimmed[(colon + 1)..].Trim().Trim('\'', '"');
                        if (k == "display_name")
                        {
                            _locations[currentKey] = val;
                        }
                    }
                }
            }
            else if (section == "assets")
            {
                if (trimmed.StartsWith("- id:"))
                {
                    currentAsset = new AudioAssetMetadata
                    {
                        Id = trimmed[5..].Trim().Trim('\'', '"')
                    };
                    _assets.Add(currentAsset);
                    subSection = "";
                    subSubSection = "";
                    continue;
                }

                if (currentAsset == null) continue;

                if (indent == 2)
                {
                    int colon = trimmed.IndexOf(':');
                    if (colon > 0)
                    {
                        string k = trimmed[..colon].Trim();
                        string val = trimmed[(colon + 1)..].Trim().Trim('\'', '"');
                        subSection = k;
                        subSubSection = "";

                        if (k == "audio_type") currentAsset.AudioType = val;
                        else if (k == "speaker_id") currentAsset.SpeakerId = val;
                        else if (k == "notes" || k == "note") currentAsset.Notes = val;
                        else if (k == "category") currentAsset.Category = val;
                        else if (k == "area") currentAsset.Area = val;
                        else if (k == "nickname") currentAsset.Nickname = val;
                    }
                }
                else if (indent == 4)
                {
                    if (trimmed.StartsWith("- "))
                    {
                        string val = trimmed[2..].Trim().Trim('\'', '"');
                        if (subSection == "source" && subSubSection == "file_patterns")
                        {
                            currentAsset.FilePatterns.Add(val);
                            try
                            {
                                string regexStr = "^" + Regex.Escape(val.ToLowerInvariant())
                                    .Replace(@"\#\#\#\#\#\#\#", "[0-9a-f]{7}") + "$";
                                currentAsset.PatternRegexes.Add(new Regex(regexStr, RegexOptions.IgnoreCase | RegexOptions.Compiled));
                            }
                            catch { }
                        }
                        else if (subSection == "usage")
                        {
                            if (_locations.TryGetValue(val, out var disp)) val = disp;
                            if (!currentAsset.Locations.Contains(val))
                                currentAsset.Locations.Add(val);
                        }
                    }
                    else
                    {
                        int colon = trimmed.IndexOf(':');
                        if (colon > 0)
                        {
                            string k = trimmed[..colon].Trim();
                            string val = trimmed[(colon + 1)..].Trim().Trim('\'', '"');
                            subSubSection = k;

                            if (subSection == "source")
                            {
                                if (k == "scope") currentAsset.Scope = val;
                                else if (k == "original_directory") currentAsset.OriginalDirectory = val;
                            }
                        }
                    }
                }
                else if (indent == 6)
                {
                    if (trimmed.StartsWith("- "))
                    {
                        string val = trimmed[2..].Trim().Trim('\'', '"');
                        if (subSubSection == "file_patterns")
                        {
                            currentAsset.FilePatterns.Add(val);
                            try
                            {
                                string regexStr = "^" + Regex.Escape(val.ToLowerInvariant())
                                    .Replace(@"\#\#\#\#\#\#\#", "[0-9a-f]{7}") + "$";
                                currentAsset.PatternRegexes.Add(new Regex(regexStr, RegexOptions.IgnoreCase | RegexOptions.Compiled));
                            }
                            catch { }
                        }
                    }
                    else
                    {
                        int colon = trimmed.IndexOf(':');
                        if (colon > 0)
                        {
                            string k = trimmed[..colon].Trim();
                            string val = trimmed[(colon + 1)..].Trim().Trim('\'', '"');
                            if (k.Equals("file_patterns", StringComparison.OrdinalIgnoreCase))
                            {
                                subSubSection = "file_patterns";
                            }
                            else if (k.Equals("Note", StringComparison.OrdinalIgnoreCase) && string.IsNullOrEmpty(currentAsset.Notes))
                            {
                                currentAsset.Notes = val;
                            }
                            else if (k.Equals("CharacterName", StringComparison.OrdinalIgnoreCase) && string.IsNullOrEmpty(currentAsset.SpeakerName))
                            {
                                currentAsset.SpeakerName = val;
                            }
                            else if (k.Equals("Level", StringComparison.OrdinalIgnoreCase) && currentAsset.Locations.Count == 0 && val != "TBD")
                            {
                                currentAsset.Locations.Add(val);
                            }
                        }
                    }
                }
                else if (indent == 8)
                {
                    int colon = trimmed.IndexOf(':');
                    if (colon > 0)
                    {
                        string k = trimmed[..colon].Trim();
                        string val = trimmed[(colon + 1)..].Trim().Trim('\'', '"');
                        if (k.Equals("file_pattern", StringComparison.OrdinalIgnoreCase))
                        {
                            if (!currentAsset.FilePatterns.Contains(val))
                                currentAsset.FilePatterns.Add(val);
                        }
                        else if (k.Equals("file_regex", StringComparison.OrdinalIgnoreCase))
                        {
                            try
                            {
                                currentAsset.PatternRegexes.Add(new Regex(val, RegexOptions.IgnoreCase | RegexOptions.Compiled));
                            }
                            catch { }
                        }
                    }
                }
            }
        }

        // Link speakers
        foreach (var asset in _assets)
        {
            if (!string.IsNullOrEmpty(asset.SpeakerId) && _speakers.TryGetValue(asset.SpeakerId, out var spk))
            {
                asset.SpeakerName = spk.Name;
                asset.SpeakerStatus = spk.Status;
            }
        }

        _loaded = true;
    }

    public AudioAssetMetadata? FindMetadata(string path, string filename)
    {
        if (!_loaded || _assets.Count == 0) return null;

        string normPath = path.Replace('\\', '/').ToLowerInvariant();
        string normFile = (string.IsNullOrEmpty(filename) ? Path.GetFileName(normPath) : filename).ToLowerInvariant();

        string scope = normPath.Contains("/global/") ? "global" :
                       (normPath.Contains("/en/") || normPath.Contains("/fr/") || normPath.Contains("/it/") || normPath.Contains("/es/")) ? "localized" : "";

        AudioAssetMetadata? best = null;
        int bestScore = -1;

        foreach (var asset in _assets)
        {
            bool matches = false;
            foreach (var regex in asset.PatternRegexes)
            {
                if (regex.IsMatch(normFile))
                {
                    matches = true;
                    break;
                }
            }

            if (!matches)
            {
                foreach (var p in asset.FilePatterns)
                {
                    if (normFile.Equals(p, StringComparison.OrdinalIgnoreCase))
                    {
                        matches = true;
                        break;
                    }
                }
            }

            if (!matches) continue;

            int score = 1;
            if (!string.IsNullOrEmpty(asset.OriginalDirectory) &&
                normPath.Contains("/" + asset.OriginalDirectory.ToLowerInvariant() + "/"))
            {
                score += 5;
            }

            if (!string.IsNullOrEmpty(scope) && !string.IsNullOrEmpty(asset.Scope) &&
                scope.Equals(asset.Scope, StringComparison.OrdinalIgnoreCase))
            {
                score += 2;
            }

            if (score > bestScore)
            {
                bestScore = score;
                best = asset;
            }
        }

        return best;
    }

    public string FormatDescription(string path, string filename, long fileSize)
    {
        string normFile = string.IsNullOrEmpty(filename) ? Path.GetFileName(path) : filename;
        string ext = Path.GetExtension(normFile).ToLowerInvariant();
        var sb = new System.Text.StringBuilder();

        string kind = ext switch
        {
            ".snu" or ".snr" or ".mus" or ".sbk" or ".wav" or ".ogg" or ".mp3" or ".flac" => "Audio",
            ".vp6" or ".mp4" or ".ogv" or ".avi" or ".webm" => "Video",
            ".png" or ".dds" or ".jpg" or ".jpeg" or ".bmp" or ".tga" => "Image",
            _ => "Media"
        };

        sb.AppendLine($"{kind}: {normFile}");
        sb.AppendLine($"Size: {fileSize:N0} bytes");
        sb.AppendLine();

        if (ext == ".snu")
        {
            sb.AppendLine("EA streamed audio (.exa.snu / SNU wrapper).");
            sb.AppendLine("Play decodes this stream to a temporary PCM WAV and opens it in the Windows default player.");
            sb.AppendLine("Four-channel streams produce separate front and rear stereo WAVs, as in operation 12.");
            sb.AppendLine();
        }
        else if (ext == ".mus")
        {
            sb.AppendLine("Interactive music archive containing SNR/SNS segment pairs.");
            sb.AppendLine("Play extracts the descriptor-selected segments and decodes them to temporary WAV files (operation 13).");
            sb.AppendLine("Segment numbers are retained; original adaptive sequencing is not reconstructed.");
            sb.AppendLine();
        }
        else if (ext == ".sbk")
        {
            sb.AppendLine("EA sound bank containing one or more subsongs.");
            sb.AppendLine("Play decodes its tracks to temporary WAV files (operation 11). Select a decoded track to hear it.");
            sb.AppendLine();
        }
        else if (ext == ".vp6")
        {
            sb.AppendLine("EA movie container carrying VP6 video and associated audio.");
            sb.AppendLine("Watch converts this movie to temporary OGV (Theora/Vorbis), matching operation 14, then opens the default player.");
            sb.AppendLine();
        }

        var meta = FindMetadata(path, normFile);
        if (meta != null)
        {
            sb.AppendLine("Status: AudioMap V2 association");
            sb.AppendLine($"Asset: {meta.Id}");
            if (!string.IsNullOrEmpty(meta.AudioType)) sb.AppendLine($"Type: {meta.AudioType}");
            if (!string.IsNullOrEmpty(meta.Scope)) sb.AppendLine($"Scope: {meta.Scope}");
            if (!string.IsNullOrEmpty(meta.SpeakerName)) sb.AppendLine($"Speaker: {meta.SpeakerName}");
            if (!string.IsNullOrEmpty(meta.SpeakerStatus)) sb.AppendLine($"Review Status: {meta.SpeakerStatus}");
            if (meta.Locations.Count > 0) sb.AppendLine($"Locations: {string.Join(", ", meta.Locations)}");
            if (!string.IsNullOrEmpty(meta.OriginalDirectory)) sb.AppendLine($"Source Bank: {meta.OriginalDirectory}");
            if (!string.IsNullOrEmpty(meta.Category)) sb.AppendLine($"Category: {meta.Category}");
            if (!string.IsNullOrEmpty(meta.Area)) sb.AppendLine($"Area: {meta.Area}");
            if (!string.IsNullOrEmpty(meta.Nickname)) sb.AppendLine($"Nickname: {meta.Nickname}");
            if (!string.IsNullOrEmpty(meta.Notes)) sb.AppendLine($"Notes: {meta.Notes}");
            sb.AppendLine();
            sb.AppendLine("Association source: reversing/docs/PS3_GAME/USRDIR/A1_Audio/AudioMap.yaml");
            sb.AppendLine("Registry associations do not establish original event timing or playback conditions.");
        }
        else if (ext is ".snu" or ".snr")
        {
            sb.AppendLine("Status: No AudioMap association recorded for this filename");
            sb.AppendLine("Association source: reversing/docs/PS3_GAME/USRDIR/A1_Audio/AudioMap.yaml");
        }

        return sb.ToString();
    }
}
