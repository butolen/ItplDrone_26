using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Security.Principal;

const int WebGuiPort = 5763;
const int PcQgcPort = 5764;
const int PhoneQgcPort = 5765;
const string GuiUrl = "http://localhost:5102/procedure";

var options = LauncherOptions.Parse(args);
if (options.ShowHelp)
{
    PrintHelp();
    return 0;
}

var repoRoot = FindRepoRoot();
var startedProcesses = new List<ManagedProcess>();
var stopRequested = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
var stopping = false;

Console.CancelKeyPress += (_, eventArgs) =>
{
    eventArgs.Cancel = true;
    stopRequested.TrySetResult();
};

Console.WriteLine("DroneForge Launcher");
Console.WriteLine("===================");
Console.WriteLine($"Repo: {repoRoot}");
Console.WriteLine();

try
{
    if (!options.SkipPortProxy)
    {
        await ConfigurePortProxyAsync();
    }

    if (!options.SkipSitl)
    {
        startedProcesses.Add(StartSitl());
    }

    if (!options.SkipApi)
    {
        await InstallApiRequirementsAsync();
        startedProcesses.Add(StartApi());
    }

    if (!options.SkipGui)
    {
        startedProcesses.Add(StartGui());
        _ = OpenGuiAfterDelayAsync();
    }

    Console.WriteLine();
    Console.WriteLine("Laeuft. WebGUI/API: tcp:127.0.0.1:5763");
    Console.WriteLine("PC-QGroundControl: 127.0.0.1:5764");
    Console.WriteLine("Handy-QGroundControl: <Windows-PC-IP>:5765");
    Console.WriteLine();
    Console.WriteLine("Zum Beenden: q oder Ctrl+C.");

    while (!stopRequested.Task.IsCompleted)
    {
        try
        {
            if (Console.KeyAvailable)
            {
                var key = Console.ReadKey(intercept: true);
                if (key.Key is ConsoleKey.Q or ConsoleKey.Escape)
                {
                    stopRequested.TrySetResult();
                }
            }
        }
        catch (InvalidOperationException)
        {
            // Non-interactive terminals may not support KeyAvailable.
        }

        await Task.WhenAny(Task.Delay(250), stopRequested.Task);
    }

    await StopAsync();
    return 0;
}
catch (Exception ex)
{
    Console.WriteLine();
    Console.WriteLine($"Launcher-Fehler: {ex.Message}");
    stopRequested.TrySetResult();
    await StopAsync();
    return 1;
}

async Task ConfigurePortProxyAsync()
{
    if (!OperatingSystem.IsWindows())
    {
        Console.WriteLine("[ports] Portproxy wird nur unter Windows eingerichtet.");
        return;
    }

    if (!IsAdministrator())
    {
        Console.WriteLine("[ports] Nicht als Administrator gestartet.");
        Console.WriteLine("[ports] Lokale Verbindungen koennen trotzdem funktionieren, aber Handy-TCP braucht die Portproxy-Regeln.");
        Console.WriteLine("[ports] Starte PowerShell/Rider als Administrator oder fuehre die Befehle aus Start.txt einmal manuell aus.");
        return;
    }

    var wslIpResult = await RunCaptureAsync(
        "wsl.exe",
        ["hostname", "-I"],
        repoRoot);

    var wslIp = wslIpResult.Output
        .Split([' ', '\r', '\n', '\t'], StringSplitOptions.RemoveEmptyEntries)
        .FirstOrDefault();

    if (string.IsNullOrWhiteSpace(wslIp))
    {
        Console.WriteLine("[ports] Konnte WSL-IP nicht ermitteln. Portproxy wird uebersprungen.");
        return;
    }

    Console.WriteLine($"[ports] WSL-IP: {wslIp}");

    foreach (var port in new[] { WebGuiPort, PcQgcPort, PhoneQgcPort })
    {
        await RunBestEffortAsync("netsh", ["interface", "portproxy", "delete", "v4tov4", $"listenaddress=0.0.0.0", $"listenport={port}"], repoRoot);
        await RunBestEffortAsync("netsh", ["interface", "portproxy", "add", "v4tov4", $"listenaddress=0.0.0.0", $"listenport={port}", $"connectaddress={wslIp}", $"connectport={port}"], repoRoot);
        await RunBestEffortAsync("netsh", ["advfirewall", "firewall", "delete", "rule", $"name=DroneForge MAVLink TCP {port}"], repoRoot);
        await RunBestEffortAsync("netsh", ["advfirewall", "firewall", "add", "rule", $"name=DroneForge MAVLink TCP {port}", "dir=in", "action=allow", "protocol=TCP", $"localport={port}"], repoRoot);
    }

    Console.WriteLine("[ports] Portproxy und Firewall-Regeln sind eingerichtet.");
}

ManagedProcess StartSitl()
{
    var sitlCommand =
        "cd ~/ardupilot/ArduCopter && " +
        "../Tools/autotest/sim_vehicle.py -v ArduCopter -f quad --console --wipe --location=MeinStandort " +
        $"--out=tcpin:0.0.0.0:{WebGuiPort} " +
        $"--out=tcpin:0.0.0.0:{PcQgcPort} " +
        $"--out=tcpin:0.0.0.0:{PhoneQgcPort}";

    if (options.WithUdp)
    {
        sitlCommand += " --out=udp:192.168.240.1:14550";
    }

    return StartManaged("sitl", "wsl.exe", ["bash", "-lc", sitlCommand], repoRoot);
}

async Task InstallApiRequirementsAsync()
{
    if (options.SkipInstall)
    {
        return;
    }

    var python = ResolvePython(repoRoot);
    var apiDir = Path.Combine(repoRoot, "DroneApi");

    Console.WriteLine("[api] Installiere/pruefe Python-Abhaengigkeiten...");
    var result = await RunCaptureAsync(python, ["-m", "pip", "install", "-r", "requirements.txt"], apiDir);
    if (result.ExitCode != 0)
    {
        Console.WriteLine(result.Output);
        throw new InvalidOperationException("Python-Abhaengigkeiten konnten nicht installiert werden.");
    }
}

ManagedProcess StartApi()
{
    var python = ResolvePython(repoRoot);
    var apiDir = Path.Combine(repoRoot, "DroneApi");
    return StartManaged("api", python, ["main.py"], apiDir);
}

ManagedProcess StartGui()
{
    return StartManaged(
        "gui",
        "dotnet",
        ["run", "--project", Path.Combine(repoRoot, "ITPDroneGUI", "ITPDroneGUI.csproj"), "--launch-profile", "http"],
        repoRoot);
}

async Task OpenGuiAfterDelayAsync()
{
    if (!options.OpenBrowser)
    {
        return;
    }

    await Task.Delay(TimeSpan.FromSeconds(8));
    if (stopping)
    {
        return;
    }

    try
    {
        Process.Start(new ProcessStartInfo
        {
            FileName = GuiUrl,
            UseShellExecute = true,
        });
    }
    catch
    {
        Console.WriteLine($"[gui] Browser konnte nicht automatisch geoeffnet werden: {GuiUrl}");
    }
}

ManagedProcess StartManaged(string name, string fileName, IReadOnlyList<string> arguments, string workingDirectory)
{
    var process = new Process
    {
        StartInfo = new ProcessStartInfo
        {
            FileName = fileName,
            WorkingDirectory = workingDirectory,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        },
        EnableRaisingEvents = true,
    };

    foreach (var argument in arguments)
    {
        process.StartInfo.ArgumentList.Add(argument);
    }

    process.OutputDataReceived += (_, eventArgs) =>
    {
        if (!string.IsNullOrWhiteSpace(eventArgs.Data))
        {
            Console.WriteLine($"[{name}] {eventArgs.Data}");
        }
    };

    process.ErrorDataReceived += (_, eventArgs) =>
    {
        if (!string.IsNullOrWhiteSpace(eventArgs.Data))
        {
            Console.WriteLine($"[{name}] {eventArgs.Data}");
        }
    };

    if (!process.Start())
    {
        throw new InvalidOperationException($"{name} konnte nicht gestartet werden.");
    }

    process.BeginOutputReadLine();
    process.BeginErrorReadLine();
    Console.WriteLine($"[{name}] gestartet: {fileName} {string.Join(' ', arguments)}");
    return new ManagedProcess(name, process);
}

async Task StopAsync()
{
    if (stopping)
    {
        return;
    }

    stopping = true;
    Console.WriteLine();
    Console.WriteLine("Stoppe DroneForge...");

    foreach (var managed in startedProcesses.AsEnumerable().Reverse())
    {
        await managed.StopAsync();
    }

    if (!options.SkipSitl)
    {
        await StopSitlInWslAsync();
    }

    Console.WriteLine("Fertig gestoppt.");
}

async Task StopSitlInWslAsync()
{
    if (!OperatingSystem.IsWindows())
    {
        return;
    }

    await RunBestEffortAsync(
        "wsl.exe",
        ["bash", "-lc", "pkill -f 'sim_vehicle.py.*ArduCopter' || true; pkill -f 'MAVProxy' || true; pkill -f 'arducopter' || true"],
        repoRoot);
}

static string ResolvePython(string root)
{
    var venvPython = Path.Combine(root, ".venv", "Scripts", "python.exe");
    return File.Exists(venvPython) ? venvPython : "python";
}

static string FindRepoRoot()
{
    var directory = AppContext.BaseDirectory;

    while (!string.IsNullOrWhiteSpace(directory))
    {
        if (Directory.Exists(Path.Combine(directory, "DroneApi")) &&
            Directory.Exists(Path.Combine(directory, "ITPDroneGUI")))
        {
            return directory;
        }

        var parent = Directory.GetParent(directory);
        if (parent is null)
        {
            break;
        }

        directory = parent.FullName;
    }

    return Directory.GetCurrentDirectory();
}

static bool IsAdministrator()
{
    if (!OperatingSystem.IsWindows())
    {
        return false;
    }

    using var identity = WindowsIdentity.GetCurrent();
    var principal = new WindowsPrincipal(identity);
    return principal.IsInRole(WindowsBuiltInRole.Administrator);
}

static async Task RunBestEffortAsync(string fileName, IReadOnlyList<string> arguments, string workingDirectory)
{
    var result = await RunCaptureAsync(fileName, arguments, workingDirectory);
    if (result.ExitCode != 0 && !string.IsNullOrWhiteSpace(result.Output))
    {
        Console.WriteLine(result.Output.Trim());
    }
}

static async Task<CaptureResult> RunCaptureAsync(string fileName, IReadOnlyList<string> arguments, string workingDirectory)
{
    using var process = new Process
    {
        StartInfo = new ProcessStartInfo
        {
            FileName = fileName,
            WorkingDirectory = workingDirectory,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        },
    };

    foreach (var argument in arguments)
    {
        process.StartInfo.ArgumentList.Add(argument);
    }

    process.Start();
    var stdout = await process.StandardOutput.ReadToEndAsync();
    var stderr = await process.StandardError.ReadToEndAsync();
    await process.WaitForExitAsync();

    var output = string.Join(Environment.NewLine, new[] { stdout, stderr }.Where(text => !string.IsNullOrWhiteSpace(text)));
    return new CaptureResult(process.ExitCode, output);
}

static void PrintHelp()
{
    Console.WriteLine("DroneForge Launcher");
    Console.WriteLine();
    Console.WriteLine("Start:");
    Console.WriteLine("  cd DroneLauncher");
    Console.WriteLine("  dotnet run");
    Console.WriteLine();
    Console.WriteLine("Oder aus dem Repo-Ordner:");
    Console.WriteLine("  dotnet run --project DroneLauncher");
    Console.WriteLine();
    Console.WriteLine("Optionen:");
    Console.WriteLine("  --skip-sitl       Startet ArduCopter SITL nicht.");
    Console.WriteLine("  --skip-api        Startet die FastAPI nicht.");
    Console.WriteLine("  --skip-gui        Startet die Blazor-WebGUI nicht.");
    Console.WriteLine("  --skip-portproxy  Richtet keine Windows-Portproxy-Regeln ein.");
    Console.WriteLine("  --skip-install    Fuehrt pip install nicht aus.");
    Console.WriteLine("  --no-browser      Oeffnet den Browser nicht automatisch.");
    Console.WriteLine("  --with-udp        Fuegt zusaetzlich UDP 192.168.240.1:14550 hinzu.");
    Console.WriteLine("  --help            Zeigt diese Hilfe.");
}

sealed record CaptureResult(int ExitCode, string Output);

sealed class ManagedProcess(string name, Process process)
{
    public async Task StopAsync()
    {
        if (process.HasExited)
        {
            Console.WriteLine($"[{name}] war schon beendet.");
            return;
        }

        Console.WriteLine($"[{name}] beenden...");

        try
        {
            process.Kill(entireProcessTree: true);
            await process.WaitForExitAsync();
        }
        catch (Exception ex)
        {
            Console.WriteLine($"[{name}] konnte nicht sauber beendet werden: {ex.Message}");
        }
    }
}

sealed record LauncherOptions
{
    public bool SkipSitl { get; init; }
    public bool SkipApi { get; init; }
    public bool SkipGui { get; init; }
    public bool SkipPortProxy { get; init; }
    public bool SkipInstall { get; init; }
    public bool OpenBrowser { get; init; } = true;
    public bool WithUdp { get; init; }
    public bool ShowHelp { get; init; }

    public static LauncherOptions Parse(string[] args)
    {
        var options = new LauncherOptions();

        foreach (var arg in args)
        {
            options = arg.ToLowerInvariant() switch
            {
                "--skip-sitl" => options with { SkipSitl = true },
                "--skip-api" => options with { SkipApi = true },
                "--skip-gui" => options with { SkipGui = true },
                "--skip-portproxy" => options with { SkipPortProxy = true },
                "--skip-install" => options with { SkipInstall = true },
                "--no-browser" => options with { OpenBrowser = false },
                "--with-udp" => options with { WithUdp = true },
                "--help" or "-h" or "/?" => options with { ShowHelp = true },
                _ => options,
            };
        }

        return options;
    }
}
