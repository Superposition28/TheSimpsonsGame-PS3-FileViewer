using System.Diagnostics;
using System.Net.Sockets;

namespace TheSimpsonsGame.FileViewer.Connections;

public class ServerController : IDisposable
{
    private ConnectionsWebServer? _server;

    public bool IsRunning => _server?.IsRunning ?? false;
    public int Port => _server?.Port ?? 0;
    public string Url => $"http://127.0.0.1:{Port}/";

    public bool Start(string databasePath, string webRoot, string docsRoot, int port = 8781)
    {
        Stop();
        if (port == 0) port = GetFreePort();

        try
        {
            _server = new ConnectionsWebServer(databasePath, webRoot, docsRoot, port);
            _server.Start();
            return true;
        }
        catch
        {
            _server = null;
            return false;
        }
    }

    public void Stop()
    {
        if (_server != null)
        {
            _server.Dispose();
            _server = null;
        }
    }

    public void OpenBrowser()
    {
        if (IsRunning)
        {
            try
            {
                Process.Start(new ProcessStartInfo
                {
                    FileName = Url,
                    UseShellExecute = true
                });
            }
            catch { }
        }
    }

    public void Dispose()
    {
        Stop();
    }

    private static int GetFreePort()
    {
        var listener = new TcpListener(System.Net.IPAddress.Loopback, 0);
        listener.Start();
        int port = ((System.Net.IPEndPoint)listener.LocalEndpoint).Port;
        listener.Stop();
        return port;
    }
}

