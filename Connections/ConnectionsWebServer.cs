using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using System.Web;
using TheSimpsonsGame.FileViewer.Formats;

namespace TheSimpsonsGame.FileViewer.Connections;

public class ConnectionsWebServer : IDisposable
{
    private TcpListener _listener;
    private readonly ConnectionExplorer _explorer;
    private readonly string _webRoot;
    private readonly string _docsRoot;
    private readonly CancellationTokenSource _cts = new();
    private Task? _listenerTask;

    public int Port { get; private set; }
    public bool IsRunning { get; private set; }

    public ConnectionsWebServer(string databasePath, string webRoot, string docsRoot, int port = 8781)
    {
        _explorer = new ConnectionExplorer(databasePath);
        _webRoot = ResolveWebRoot(webRoot);
        _docsRoot = docsRoot;
        Port = port;

        _listener = new TcpListener(IPAddress.Loopback, port);
    }

    private static string ResolveWebRoot(string webRoot)
    {
        if (File.Exists(Path.Combine(webRoot, "index.html"))) return Path.GetFullPath(webRoot);

        string pyCandidate = Path.Combine(webRoot, "..", ".py", "connection_explorer", "web");
        if (File.Exists(Path.Combine(pyCandidate, "index.html"))) return Path.GetFullPath(pyCandidate);

        string appCandidate = Path.Combine(AppContext.BaseDirectory, "connection_explorer", "web");
        if (File.Exists(Path.Combine(appCandidate, "index.html"))) return Path.GetFullPath(appCandidate);

        return webRoot;
    }

    public void Start()
    {
        if (IsRunning) return;
        try
        {
            _listener.Start();
        }
        catch (SocketException)
        {
            _listener = new TcpListener(IPAddress.Loopback, 0);
            _listener.Start();
        }

        Port = ((IPEndPoint)_listener.LocalEndpoint).Port;
        IsRunning = true;
        _listenerTask = Task.Run(ListenLoop);
    }

    public void Stop()
    {
        if (!IsRunning) return;
        IsRunning = false;
        _cts.Cancel();
        try { _listener.Stop(); } catch { }
    }

    public void Dispose()
    {
        Stop();
        _explorer.Dispose();
        _cts.Dispose();
    }

    private async Task ListenLoop()
    {
        while (!_cts.IsCancellationRequested && IsRunning)
        {
            try
            {
                var client = await _listener.AcceptTcpClientAsync(_cts.Token);
                _ = Task.Run(() => HandleClient(client));
            }
            catch (OperationCanceledException)
            {
                break;
            }
            catch (SocketException)
            {
                break;
            }
            catch
            {
                // Continue listening
            }
        }
    }

    private async Task HandleClient(TcpClient client)
    {
        using (client)
        {
            try
            {
                using var stream = client.GetStream();
                using var reader = new StreamReader(stream, Encoding.UTF8, leaveOpen: true);

                string? requestLine = await reader.ReadLineAsync();
                if (string.IsNullOrEmpty(requestLine)) return;

                var parts = requestLine.Split(' ');
                if (parts.Length < 2) return;

                string method = parts[0];
                string fullUrl = parts[1];

                // Read headers
                var headers = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
                string? headerLine;
                while (!string.IsNullOrEmpty(headerLine = await reader.ReadLineAsync()))
                {
                    int colon = headerLine.IndexOf(':');
                    if (colon > 0)
                    {
                        headers[headerLine[..colon].Trim()] = headerLine[(colon + 1)..].Trim();
                    }
                }

                // Security check: loopback host required
                string host = headers.TryGetValue("Host", out var hVal) ? hVal.Split(':')[0] : "";
                if (host != "127.0.0.1" && host != "localhost")
                {
                    await SendJsonAsync(stream, new { error = "loopback Host required" }, 403);
                    return;
                }

                // Parse path & query
                int qIdx = fullUrl.IndexOf('?');
                string path = qIdx >= 0 ? fullUrl[..qIdx] : fullUrl;
                string queryStr = qIdx >= 0 ? fullUrl[(qIdx + 1)..] : "";
                var query = HttpUtility.ParseQueryString(queryStr);

                if (path == "/api/summary")
                {
                    var summary = _explorer.GetSummary();
                    await SendJsonAsync(stream, summary);
                }
                else if (path == "/api/files")
                {
                    string level = query["level"] ?? "";
                    string q = query["q"] ?? "";
                    string view = query["view"] ?? "member";
                    string format = query["format"] ?? "";
                    int offset = int.TryParse(query["offset"], out int off) ? off : 0;
                    int limit = int.TryParse(query["limit"], out int lim) ? Math.Clamp(lim, 1, 200) : 80;
                    bool shared = query["shared"] == "1";

                    var result = _explorer.SearchFiles(level, q, view, format, offset, limit, shared);
                    await SendJsonAsync(stream, result);
                }
                else if (path == "/api/file")
                {
                    long id = long.TryParse(query["id"], out long fid) ? fid : 0;
                    int offset = int.TryParse(query["offset"], out int off) ? off : 0;
                    int limit = int.TryParse(query["limit"], out int lim) ? Math.Clamp(lim, 1, 200) : 60;
                    string view = query["view"] ?? "member";
                    bool cross = query["cross"] == "1";
                    string language = query["language"] ?? "auto";

                    var result = _explorer.GetFileIdentifiers(id, offset, limit, view, cross, language);
                    await SendJsonAsync(stream, result);
                }
                else if (path == "/api/graph")
                {
                    long id = long.TryParse(query["id"], out long fid) ? fid : 0;
                    int depth = int.TryParse(query["depth"], out int d) ? Math.Clamp(d, 1, 3) : 1;
                    int maximum = int.TryParse(query["maximum"], out int m) ? Math.Clamp(m, 20, 500) : 160;
                    bool incoming = query["incoming"] == "1";
                    string view = query["view"] ?? "member";
                    bool cross = query["cross"] == "1";
                    string language = query["language"] ?? "auto";

                    var result = _explorer.GetGraph(id, depth, maximum, incoming, view, cross, language);
                    await SendJsonAsync(stream, result);
                }
                else if (path == "/api/words")
                {
                    long id = long.TryParse(query["id"], out long fid) ? fid : 0;
                    int offset = int.TryParse(query["offset"], out int off) ? off : 0;
                    int limit = int.TryParse(query["limit"], out int lim) ? Math.Clamp(lim, 1, 128) : 64;
                    int stride = query["unaligned"] == "1" ? 1 : 4;

                    var result = _explorer.GetWords(id, offset, limit, stride);
                    await SendJsonAsync(stream, result);
                }
                else if (path == "/api/structure")
                {
                    long id = long.TryParse(query["id"], out long fid) ? fid : 0;
                    var file = _explorer.GetFile(id);
                    if (file == null) throw new InvalidOperationException("File not found");

                    long size = Convert.ToInt64(file["size"]);
                    if (size > 32 * 1024 * 1024)
                        throw new InvalidOperationException("Structural view limit is 32 MiB; use the raw word view for this file");

                    byte[] data = _explorer.ReadFileBytes(file);
                    string member = file["member"]?.ToString() ?? "";
                    string filePath = file["path"]?.ToString() ?? "";
                    string locJson = file["locator"]?.ToString() ?? "{}";
                    string resourceType = "";
                    try
                    {
                        using var doc = JsonDocument.Parse(locJson);
                        if (doc.RootElement.TryGetProperty("resource_type", out var rt))
                            resourceType = rt.GetString() ?? "";
                    }
                    catch { }

                    var parsed = ResourceDispatcher.Parse(data, !string.IsNullOrEmpty(member) ? member : filePath, resourceType);
                    await SendJsonAsync(stream, new
                    {
                        format = parsed.Format,
                        summary = parsed.Summary,
                        structure = parsed.Structure,
                        identifiers = parsed.Identifiers,
                        identifier_status = parsed.IdentifierStatus
                    });
                }
                else if (path == "/api/copies")
                {
                    long id = long.TryParse(query["id"], out long fid) ? fid : 0;
                    var result = _explorer.GetCopies(id);
                    await SendJsonAsync(stream, result);
                }
                else if (path == "/api/catalog")
                {
                    var catalog = GetCatalog();
                    await SendJsonAsync(stream, catalog);
                }
                else if (path.StartsWith("/docs/"))
                {
                    await ServeStaticFileAsync(stream, _docsRoot, path[6..]);
                }
                else
                {
                    string rel = path == "/" ? "index.html" : path.TrimStart('/');
                    await ServeStaticFileAsync(stream, _webRoot, rel);
                }
            }
            catch (Exception ex)
            {
                try
                {
                    using var stream = client.GetStream();
                    await SendJsonAsync(stream, new { error = ex.Message }, 400);
                }
                catch { }
            }
        }
    }

    private static async Task ServeStaticFileAsync(Stream stream, string root, string relativePath)
    {
        string safePath = Path.Combine(root, relativePath.Replace('/', Path.DirectorySeparatorChar));
        string fullRoot = Path.GetFullPath(root);
        string fullTarget = Path.GetFullPath(safePath);

        if (!fullTarget.StartsWith(fullRoot, StringComparison.OrdinalIgnoreCase) || !File.Exists(fullTarget))
        {
            await SendJsonAsync(stream, new { error = "not found" }, 404);
            return;
        }

        string ext = Path.GetExtension(fullTarget).ToLowerInvariant();
        string mime = ext switch
        {
            ".html" => "text/html",
            ".css" => "text/css",
            ".js" => "text/javascript",
            ".json" => "application/json",
            ".png" => "image/png",
            _ => "application/octet-stream"
        };

        byte[] bytes = await File.ReadAllBytesAsync(fullTarget);
        await SendResponseAsync(stream, bytes, $"{mime}; charset=utf-8", 200);
    }

    private static async Task SendJsonAsync(Stream stream, object data, int status = 200)
    {
        byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(data);
        await SendResponseAsync(stream, bytes, "application/json; charset=utf-8", status);
    }

    private static async Task SendResponseAsync(Stream stream, byte[] payload, string contentType, int statusCode)
    {
        string statusText = statusCode switch
        {
            200 => "OK",
            400 => "Bad Request",
            403 => "Forbidden",
            404 => "Not Found",
            _ => "OK"
        };

        string headers = $"HTTP/1.1 {statusCode} {statusText}\r\n" +
                         $"Content-Type: {contentType}\r\n" +
                         $"Content-Length: {payload.Length}\r\n" +
                         "Cache-Control: no-store\r\n" +
                         "X-Content-Type-Options: nosniff\r\n" +
                         "Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'; object-src 'none'\r\n" +
                         "Connection: close\r\n\r\n";

        byte[] headerBytes = Encoding.ASCII.GetBytes(headers);
        await stream.WriteAsync(headerBytes);
        await stream.WriteAsync(payload);
        await stream.FlushAsync();
    }

    private object GetCatalog()
    {
        var formats = new List<object>();
        if (Directory.Exists(_docsRoot))
        {
            var analysisDir = Path.Combine(_docsRoot, "PS3_GAME", "FormatAnalysis");
            if (Directory.Exists(analysisDir))
            {
                var htmlFiles = Directory.GetFiles(analysisDir, "*.html", SearchOption.AllDirectories);
                foreach (var html in htmlFiles)
                {
                    string text = File.ReadAllText(html);
                    if (!text.Contains("id=\"evidence-and-limitations\"")) continue;

                    string title = Path.GetFileNameWithoutExtension(html);
                    int tStart = text.IndexOf("<title>", StringComparison.OrdinalIgnoreCase);
                    int tEnd = text.IndexOf("</title>", StringComparison.OrdinalIgnoreCase);
                    if (tStart >= 0 && tEnd > tStart)
                    {
                        title = text.Substring(tStart + 7, tEnd - tStart - 7).Trim();
                    }

                    string relDoc = Path.GetRelativePath(_docsRoot, html).Replace('\\', '/');
                    formats.Add(new
                    {
                        title,
                        doc = relDoc,
                        adapter = "Inventory + raw words/candidate matching."
                    });
                }
            }
        }

        return new
        {
            formats,
            policy = "Only documented namespaces are joined structurally. Raw equality and filename associations are labeled separately."
        };
    }
}
