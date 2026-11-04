using System.Diagnostics;
using System.Security.Cryptography;
using System.Text.Json;

namespace PakePortable;

// Pake is a command-line builder. This is a conventional console-subsystem Windows PE,
// not an encrypted script wrapper and not a packaged website/WebView2 application.
internal static class Program
{
    private static readonly JsonSerializerOptions JsonOptions = new() { WriteIndented = true };

    private static int Main(string[] args)
    {
        try
        {
            string root = Path.GetFullPath(AppContext.BaseDirectory);
            string data = Path.Combine(root, "Data");
            string node = Path.Combine(root, "App", "Node", "node.exe");
            string cli = Path.Combine(root, "App", "Cli", "node_modules", "pake-cli", "dist", "cli.js");
            if (!File.Exists(node) || !File.Exists(cli))
            {
                Console.Error.WriteLine("Pake runtime missing. Re-extract the complete official builder ZIP; do not replace individual files.");
                return 10;
            }
            Directory.CreateDirectory(data);
            TraceGuard guard = new(data);
            if (args.Length == 1 && args[0] == "--traceguard-selftest")
                return guard.RunSelfTest() ? 0 : 20;

            guard.RecoverInterruptedSession();
            var owned = guard.PrepareExternalRoots(); // only explicit, exclusive, initially absent roots
            var env = BuildPortableEnvironment(root, data);
            var psi = new ProcessStartInfo(node) { UseShellExecute = false, WorkingDirectory = Path.Combine(data, "Output") };
            Directory.CreateDirectory(psi.WorkingDirectory);
            psi.ArgumentList.Add(cli);
            foreach (var argument in args) psi.ArgumentList.Add(argument);
            foreach (var pair in env) psi.Environment[pair.Key] = pair.Value;
            int result = 1;
            guard.MarkActive(owned);
            try
            {
                using var process = Process.Start(psi) ?? throw new InvalidOperationException("Unable to start bundled Node CLI.");
                process.WaitForExit();
                result = process.ExitCode;
            }
            finally
            {
                // Never remove a host-owned directory. A failed copy leaves the source intact.
                guard.CaptureExternalRoots(owned);
                guard.RecordDataManifest();
                guard.MarkCompleted();
            }
            return result;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"Pake portable error: {ex.Message}");
            return 1;
        }
    }

    private static Dictionary<string,string> BuildPortableEnvironment(string root, string data)
    {
        string profile = Path.Combine(data, "Profile");
        string roaming = Path.Combine(profile, "AppData", "Roaming");
        string local = Path.Combine(profile, "AppData", "Local");
        string temp = Path.Combine(data, "Temp");
        string node = Path.Combine(root, "App", "Node");
        string tools = Path.Combine(root, "App", "Tools");
        var dirs = new[] { profile, roaming, local, temp, Path.Combine(data, "Cache"), Path.Combine(data, "Output"), Path.Combine(data, "Config"), Path.Combine(data, "Cache", "pnpm"), Path.Combine(data, "Cache", "npm"), Path.Combine(data, "BuildCache", "target") };
        foreach (var dir in dirs) Directory.CreateDirectory(dir);
        // Preserve the real USERPROFILE and Rustup paths: altering them without a verified
        // portable Rust installation can break Windows build tool detection.
        return new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            ["HOME"] = profile,
            ["APPDATA"] = roaming,
            ["LOCALAPPDATA"] = local,
            ["XDG_CONFIG_HOME"] = Path.Combine(data, "Config"),
            ["XDG_CACHE_HOME"] = Path.Combine(data, "Cache"),
            ["TEMP"] = temp,
            ["TMP"] = temp,
            ["npm_config_cache"] = Path.Combine(data, "Cache", "npm"),
            ["PNPM_HOME"] = Path.Combine(data, "Cache", "pnpm"),
            ["COREPACK_HOME"] = Path.Combine(data, "Cache", "corepack"),
            // Pake's enterBuildWorkspace() explicitly honors CARGO_TARGET_DIR;
            // its WinBuilder resolves MSI/raw binaries against that same cache.
            ["CARGO_TARGET_DIR"] = Path.Combine(data, "BuildCache", "target"),
            ["PAKE_PORTABLE_ROOT"] = root,
            ["PATH"] = string.Join(Path.PathSeparator, new[] { node, tools, Path.Combine(tools, "node_modules", ".bin"), Environment.GetEnvironmentVariable("PATH") ?? "" })
        };
    }

    private sealed record ExternalRoot(string Path, string Key);
    private sealed record PendingSession(DateTime StartedUtc, List<ExternalRoot> Roots);
    private sealed record DataItem(string Path, string Kind, long Length, string? Sha256);

    private sealed class TraceGuard
    {
        private readonly string data;
        private readonly string trace;
        private readonly string active;
        private readonly string manifest;
        private readonly string recovered;
        public TraceGuard(string dataPath)
        {
            data = dataPath;
            trace = Path.Combine(data, "TraceGuard");
            active = Path.Combine(trace, "active.json");
            manifest = Path.Combine(trace, "manifest.json");
            recovered = Path.Combine(trace, "Recovered");
            Directory.CreateDirectory(trace);
            Directory.CreateDirectory(recovered);
        }
        public void RecoverInterruptedSession()
        {
            if (!File.Exists(active)) return;
            Console.Error.WriteLine("TraceGuard: interrupted run detected; recovering owned roots and rescanning Data.");
            PendingSession? previous = JsonSerializer.Deserialize<PendingSession>(File.ReadAllText(active));
            if (previous != null) CaptureExternalRoots(previous.Roots, previous.StartedUtc);
            RecordDataManifest();
            File.Delete(active);
        }
        public List<ExternalRoot> PrepareExternalRoots()
        {
            // Explicit allowlist ONLY. Upstream Pake has no verified fixed host-owned
            // profile folder, so by default no host folders are monitored or moved.
            string config = Path.Combine(trace, "owned-roots.txt");
            if (!File.Exists(config)) File.WriteAllText(config, "# OPTIONAL: exclusive Pake-owned absolute folder per line. Leave empty unless verified.\n");
            var result = new List<ExternalRoot>();
            int number = 0;
            foreach (string raw in File.ReadAllLines(config))
            {
                string line = raw.Trim();
                if (line.Length == 0 || line.StartsWith('#')) continue;
                string expanded = Environment.ExpandEnvironmentVariables(line);
                if (!Path.IsPathFullyQualified(expanded)) throw new InvalidOperationException("TraceGuard allowlist requires absolute paths");
                string path = Path.GetFullPath(expanded).TrimEnd(Path.DirectorySeparatorChar);
                string name = Path.GetFileName(path);
                // Never configure shared profile roots or shared Windows folders.
                if (!name.StartsWith("PakePortable-", StringComparison.OrdinalIgnoreCase))
                    throw new InvalidOperationException("TraceGuard accepts only exclusive PakePortable-* root names");
                if (path.StartsWith(Path.GetFullPath(data), StringComparison.OrdinalIgnoreCase))
                    throw new InvalidOperationException("External TraceGuard path cannot be inside Data");
                // Stable ID even if some allowlisted roots already exist on this PC.
                var root = new ExternalRoot(path, "external-" + number++);
                if (Directory.Exists(path) || File.Exists(path))
                {
                    Console.Error.WriteLine($"TraceGuard: pre-existing host root protected, will not move: {path}");
                    continue;
                }
                string saved = Path.Combine(recovered, root.Key);
                if (Directory.Exists(saved))
                {
                    // Recreate previously captured state only when the host path is
                    // absent. Any pre-existing host path takes precedence.
                    CopyVerified(saved, path);
                    Console.WriteLine($"TraceGuard restored exclusive app root: {path}");
                }
                result.Add(root);
            }
            return result;
        }
        public void MarkActive(List<ExternalRoot> roots) => AtomicWrite(active, JsonSerializer.Serialize(new PendingSession(DateTime.UtcNow, roots), JsonOptions));
        public void MarkCompleted() { if (File.Exists(active)) File.Delete(active); }
        public void CaptureExternalRoots(List<ExternalRoot> roots, DateTime? started = null)
        {
            foreach (var root in roots)
            {
                if (!Directory.Exists(root.Path)) continue;
                try
                {
                    // Root was absent before the launch. If interrupted, reject folders
                    // predating the interrupted run to avoid taking unrelated host data.
                    if (started.HasValue && Directory.GetCreationTimeUtc(root.Path) < started.Value.AddSeconds(-5))
                    {
                        Console.Error.WriteLine($"TraceGuard: uncertain ownership; leaving host root untouched: {root.Path}");
                        continue;
                    }
                    string dest = Path.Combine(recovered, root.Key);
                    CopyVerified(root.Path, dest);
                    // Delete only the exclusive whole-root path we ourselves tracked,
                    // never a shared AppData/LocalAppData/ProgramData parent.
                    Directory.Delete(root.Path, recursive: true);
                    Console.WriteLine($"TraceGuard preserved {root.Path} -> {dest}");
                }
                catch (Exception e)
                {
                    Console.Error.WriteLine($"TraceGuard: copy/cleanup incomplete for {root.Path}: {e.Message}; source retained where possible.");
                    throw;
                }
            }
        }
        private static void CopyVerified(string source, string destination)
        {
            if ((File.GetAttributes(source) & FileAttributes.ReparsePoint) != 0)
                throw new IOException("Refusing to traverse a reparse-point source root");
            // Do not follow junctions/symlinks into unrelated host folders.
            foreach (string entry in Directory.EnumerateFileSystemEntries(source, "*", SearchOption.AllDirectories))
                if ((File.GetAttributes(entry) & FileAttributes.ReparsePoint) != 0)
                    throw new IOException($"Refusing to copy reparse point: {entry}");
            Directory.CreateDirectory(destination);
            // Enumerate directories first, including empty nested trees.
            foreach (var d in Directory.EnumerateDirectories(source, "*", SearchOption.AllDirectories))
                Directory.CreateDirectory(Path.Combine(destination, Path.GetRelativePath(source, d)));
            foreach (var f in Directory.EnumerateFiles(source, "*", SearchOption.AllDirectories))
            {
                string destFile = Path.Combine(destination, Path.GetRelativePath(source, f));
                Directory.CreateDirectory(Path.GetDirectoryName(destFile)!);
                // Do not overwrite newer recovered data silently.
                if (File.Exists(destFile) && Hash(destFile) != Hash(f))
                    throw new IOException($"Recovered file conflict: {destFile}");
                File.Copy(f, destFile, overwrite: true);
                if (Hash(f) != Hash(destFile)) throw new IOException($"SHA256 mismatch after copy: {f}");
            }
            foreach (var d in Directory.EnumerateDirectories(source, "*", SearchOption.AllDirectories))
                if (!Directory.Exists(Path.Combine(destination, Path.GetRelativePath(source, d)))) throw new IOException("Directory preservation failed");
        }
        private static string Hash(string p)
        {
            using var stream = File.OpenRead(p);
            return Convert.ToHexString(SHA256.HashData(stream));
        }
        public void RecordDataManifest()
        {
            var items = new List<DataItem>();
            // Avoid manifest self-reference. Other recovery files remain untouched.
            foreach (string d in Directory.EnumerateDirectories(data, "*", SearchOption.AllDirectories))
            {
                if (d.StartsWith(trace + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase) || string.Equals(d, trace, StringComparison.OrdinalIgnoreCase)) continue;
                items.Add(new DataItem(Path.GetRelativePath(data, d), "directory", 0, null));
            }
            foreach (string f in Directory.EnumerateFiles(data, "*", SearchOption.AllDirectories))
            {
                if (f.StartsWith(trace + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)) continue;
                var fi = new FileInfo(f);
                // Do not hash large compiler caches: their state stays within Data anyway.
                items.Add(new DataItem(Path.GetRelativePath(data, f), "file", fi.Length, null));
            }
            items.Sort((a,b) => StringComparer.OrdinalIgnoreCase.Compare(a.Path,b.Path));
            AtomicWrite(manifest, JsonSerializer.Serialize(new { version=1, scannedUtc=DateTime.UtcNow, items }, JsonOptions));
        }
        private static void AtomicWrite(string path, string content)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            string tmp = path + ".new";
            File.WriteAllText(tmp, content);
            File.Move(tmp, path, overwrite: true);
        }
        public bool RunSelfTest()
        {
            string hostRoot = Path.Combine(Path.GetTempPath(), "PakePortable-TraceGuard-Test-" + Guid.NewGuid().ToString("N"));
            string key = "selftest-" + Guid.NewGuid().ToString("N");
            string emptyNested = Path.Combine(hostRoot, "alpha", "beta", "empty");
            Directory.CreateDirectory(emptyNested);
            Directory.CreateDirectory(Path.Combine(hostRoot, "empty-top"));
            File.WriteAllText(Path.Combine(hostRoot, "alpha", "file.txt"), "traceguard test");
            CaptureExternalRoots(new List<ExternalRoot> { new(hostRoot, key) });
            string dest = Path.Combine(recovered, key);
            bool success = !Directory.Exists(hostRoot)
                && Directory.Exists(Path.Combine(dest, "alpha", "beta", "empty"))
                && Directory.Exists(Path.Combine(dest, "empty-top"))
                && File.ReadAllText(Path.Combine(dest, "alpha", "file.txt")) == "traceguard test";
            RecordDataManifest();
            Console.WriteLine(success ? "TraceGuard selftest PASS: file + empty folders + nested empty tree" : "TraceGuard selftest FAIL");
            return success;
        }
    }
}
