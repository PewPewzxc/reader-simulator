using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net.Http;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows;
using System.Windows.Interop;
using System.Windows.Media;
using Microsoft.Win32;

namespace ReaderSimulator
{
    public sealed class Build
    {
        public string Id, Name, Repo, Ref, Version, Model, Frame, Sha256;
        public Uri Url;
        public long Size;
    }

    public static class Feed
    {
        // The download list the Build firmwares workflow keeps up to date: every version offered, newest first.
        public const string FEED_URL = "https://github.com/PewPewzxc/reader-simulator/releases/download/feed/index.json";
        public static readonly string[] Models = { "X4 Pro", "X4 Classic", "X3" };
        public static readonly string[] Frames = { "x4-pro", "x4-classic", "x3" };
        // No trailing dot/dash (Windows strips trailing dots) and no reserved device names (con, nul, com1...).
        // \A..\z, not ^..$: in .NET $ also matches before a final "\n"
        static readonly Regex IdRe = new Regex(@"\A[a-z0-9](?:[a-z0-9._-]{0,98}[a-z0-9])?\z");
        static readonly Regex ReservedRe = new Regex(@"^(con|prn|aux|nul|com\d|lpt\d)(\.|$)");
        public static bool ValidId(string id) => id != null && IdRe.IsMatch(id) && !ReservedRe.IsMatch(id);
        public const int MaxFeedBytes = 4 << 20;
        public static TimeSpan StallTimeout = TimeSpan.FromSeconds(30);
        static readonly Regex HexRe = new Regex(@"\A[0-9a-f]{64}\z");
        // release-assets.githubusercontent.com: where github.com release downloads redirect to since 2025.
        static readonly string[] Hosts = { "github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com" };

        public static bool Allowed(Uri u, bool allowFile) =>
            u != null && u.IsAbsoluteUri && (u.IsFile ? allowFile && !u.IsUnc
                : u.Scheme == "https" && u.IsDefaultPort && u.UserInfo == "" && Hosts.Contains(u.Host.ToLowerInvariant()));

        public static Uri ToUri(string pathOrUrl) =>
            pathOrUrl.StartsWith("file:", StringComparison.OrdinalIgnoreCase) || pathOrUrl.StartsWith("https:", StringComparison.OrdinalIgnoreCase)
                ? new Uri(pathOrUrl) : new Uri(Path.GetFullPath(pathOrUrl));

        public static async Task<string> FetchText(Uri feed)
        {
            if (!Allowed(feed, true)) throw new InvalidOperationException("The feed address is not allowed: " + feed);
            // one path for file: and https feeds, same 4 MB cap; a unique name so two app windows starting together do not collide
            var tmp = Path.Combine(Store.Root, "feed-" + Path.GetRandomFileName() + ".download");
            try { await Download(feed, tmp, MaxFeedBytes, null, CancellationToken.None); return File.ReadAllText(tmp); }
            finally { try { File.Delete(tmp); } catch (IOException) { } } // also after a failed (offline) read
        }

        /// <summary>A version is named by its release (v1.8.1-yacp.9 -> 1.8.1-yacp.9): the number inside the source is often
        /// not updated between releases. A build from a branch is named by the branch, with that number: dev (2.3.6).</summary>
        public static string VersionLabel(string gitRef, string version) =>
            gitRef == null ? version
            : Regex.IsMatch(gitRef, @"\Av?\d") ? Regex.Replace(gitRef, @"\Av(?=\d)", "")
            : version != null && version != gitRef ? $"{gitRef} ({version})" : gitRef;

        /// <summary>Valid builds of a feed; anything malformed or not allowed is skipped.</summary>
        public static List<Build> Parse(string json, Uri feed)
        {
            var root = (Dictionary<string, object>)new JavaScriptSerializer { MaxJsonLength = MaxFeedBytes }.DeserializeObject(json);
            if (Convert.ToInt32(root["schema"]) != 1) throw new InvalidDataException("Unknown feed schema.");
            var list = new List<Build>();
            foreach (var o in (object[])root["builds"])
            {
                try
                {
                    var d = (Dictionary<string, object>)o;
                    string S(string k) => d.TryGetValue(k, out var v) && v != null ? Convert.ToString(v) : null;
                    var b = new Build
                    {
                        Id = S("id"), Name = S("name"), Repo = S("repo"), Ref = S("ref"), Version = VersionLabel(S("ref"), S("version")),
                        Model = S("model"), Frame = S("frame"), Sha256 = (S("sha256") ?? "").ToLowerInvariant(),
                        Size = d.TryGetValue("size", out var sz) ? Convert.ToInt64(sz) : 0, Url = new Uri(feed, S("url")),
                    };
                    if (ValidId(b.Id) && HexRe.IsMatch(b.Sha256) && Models.Contains(b.Model) && b.Name != null && b.Ref != null
                        && (b.Frame == null || Frames.Contains(b.Frame)) && Allowed(b.Url, feed.IsFile))
                        list.Add(b);
                }
                catch (Exception) { /* skip a malformed entry */ }
            }
            return list;
        }

        /// <summary>Downloads to <paramref name="dest"/> following only allowed redirects; returns the SHA-256 (hex).</summary>
        public static async Task<string> Download(Uri url, string dest, long maxBytes, IProgress<long> progress, CancellationToken ct)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(dest));
            using (var sha = SHA256.Create())
            using (var outStream = File.Create(dest))
            {
                Stream input; HttpResponseMessage resp = null;
                using (var http = new HttpClient(new HttpClientHandler { AllowAutoRedirect = false }) { Timeout = TimeSpan.FromSeconds(60) /* until the headers arrive */ })
                {
                    http.DefaultRequestHeaders.UserAgent.ParseAdd("ReaderSimulator/1.0");
                    if (url.IsFile) input = File.OpenRead(url.LocalPath);
                    else
                    {
                        for (int hop = 0; ; hop++)
                        {
                            if (!Allowed(url, false)) throw new InvalidOperationException("Download address not allowed: " + url.Host);
                            resp = await http.GetAsync(url, HttpCompletionOption.ResponseHeadersRead, ct);
                            int code = (int)resp.StatusCode;
                            if (code >= 300 && code < 400 && resp.Headers.Location != null && hop < 5)
                            {
                                url = new Uri(url, resp.Headers.Location); resp.Dispose(); continue;
                            }
                            resp.EnsureSuccessStatusCode();
                            break;
                        }
                        input = await resp.Content.ReadAsStreamAsync();
                    }
                    using (input)
                    using (resp)
                    {
                        var buf = new byte[1 << 16]; long total = 0; int n;
                        while ((n = await ReadOrStall(input, buf, ct)) > 0)
                        {
                            total += n;
                            if (maxBytes > 0 && total > maxBytes) throw new InvalidDataException("The download is larger than the feed says.");
                            sha.TransformBlock(buf, 0, n, null, 0);
                            await outStream.WriteAsync(buf, 0, n);
                            progress?.Report(total);
                        }
                    }
                }
                sha.TransformFinalBlock(new byte[0], 0, 0);
                return BitConverter.ToString(sha.Hash).Replace("-", "").ToLowerInvariant();
            }
        }

        /// <summary>One read that gives up after <see cref="StallTimeout"/> without data or when cancelled
        /// (the .NET Framework network stream ignores tokens, so the stream is closed instead).</summary>
        public static async Task<int> ReadOrStall(Stream s, byte[] buf, CancellationToken ct)
        {
            var read = s.ReadAsync(buf, 0, buf.Length);
            using (var t = CancellationTokenSource.CreateLinkedTokenSource(ct))
            {
                var done = await Task.WhenAny(read, Task.Delay(StallTimeout, t.Token));
                t.Cancel();
                if (done == read) return await read;
            }
            s.Dispose();
            ct.ThrowIfCancellationRequested();
            throw new TimeoutException($"No data for {StallTimeout.TotalSeconds:0} s; the download stalled.");
        }
    }

    public static class Store
    {
        public static string Root = Path.Combine(Environment.GetEnvironmentVariable("LOCALAPPDATA") is string l && l != ""
            ? l : Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "ReaderSimulator");
        public static readonly string[] PackageFiles =
            { "program.exe", "SDL2.dll", "libgcc_s_seh-1.dll", "libstdc++-6.dll", "libwinpthread-1.dll", "LICENSE-firmware.txt", "build.json" };
        public static string FramesDir => Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "frames");
        public static string SamplesDir => Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "samples");
        public static string BuildDir(Build b) => Path.Combine(Root, "builds", b.Id);
        public static string CardDir(Build b) => Path.Combine(Root, "cards", b.Id);
        public static string SdCard(Build b) => Path.Combine(CardDir(b), "fs_");
        const string ShaFile = "installed.sha256"; // the zip's SHA-256, so a folder only counts for the feed entry it came from
        public const long MaxEntryBytes = 200L << 20;
        public static bool Installed(Build b)
        {
            try { return File.Exists(Path.Combine(BuildDir(b), "program.exe")) && File.ReadAllText(Path.Combine(BuildDir(b), ShaFile)).Trim() == b.Sha256; }
            catch (Exception) { return false; } // never let a bad path crash Refresh()
        }

        /// <summary>Download, refuse a SHA-256 mismatch, unpack only the listed files.</summary>
        public static async Task Install(Build b, IProgress<long> progress, CancellationToken ct)
        {
            var builds = Path.Combine(Root, "builds");
            Directory.CreateDirectory(builds);
            // '~' is not allowed in ids, so these names can never be another build's folder
            var zip = Path.Combine(builds, b.Id + "~zip");
            var tmp = Path.Combine(builds, b.Id + "~unpacking");
            foreach (var d in Directory.GetDirectories(builds, b.Id + "~old-*")) // left by an update while that build was running
                try { Directory.Delete(d, true); } catch (Exception) { }
            try
            {
                var hash = await Feed.Download(b.Url, zip, b.Size > 0 ? b.Size : 1L << 30, progress, ct);
                if (hash != b.Sha256) throw new InvalidDataException("The download is damaged or not the one the feed lists (SHA-256 mismatch). Nothing was installed.");
                if (Directory.Exists(tmp)) Directory.Delete(tmp, true);
                Directory.CreateDirectory(tmp);
                await Task.Run(() =>
                {
                    using (var z = ZipFile.OpenRead(zip))
                        foreach (var e in z.Entries)
                        {
                            var name = PackageFiles.FirstOrDefault(f => string.Equals(f, e.FullName, StringComparison.OrdinalIgnoreCase));
                            if (name == null) continue;
                            if (e.Length > MaxEntryBytes) throw new InvalidDataException(name + " in the package is too large.");
                            // copy with a cap too: the size in a zip header can lie
                            using (var src = e.Open())
                            using (var dst = File.Create(Path.Combine(tmp, name)))
                            {
                                var buf = new byte[1 << 16]; long total = 0; int n;
                                while ((n = src.Read(buf, 0, buf.Length)) > 0)
                                {
                                    if ((total += n) > MaxEntryBytes) throw new InvalidDataException(name + " in the package is too large.");
                                    dst.Write(buf, 0, n);
                                }
                            }
                        }
                });
                if (!File.Exists(Path.Combine(tmp, "program.exe"))) throw new InvalidDataException("The package has no program.exe.");
                File.WriteAllText(Path.Combine(tmp, ShaFile), b.Sha256);
                // Move the old build aside instead of deleting it: a running simulator locks its DLLs against
                // deletion but not against renaming, so a delete would stop half-way and break the old build.
                var old = BuildDir(b) + "~old-" + Guid.NewGuid().ToString("N").Substring(0, 8);
                if (Directory.Exists(BuildDir(b))) Directory.Move(BuildDir(b), old);
                try { Directory.Move(tmp, BuildDir(b)); }
                catch (Exception) { if (Directory.Exists(old)) Directory.Move(old, BuildDir(b)); throw; }
                try { if (Directory.Exists(old)) Directory.Delete(old, true); } catch (Exception) { } // still running: removed next time
            }
            finally
            {
                try { File.Delete(zip); if (Directory.Exists(tmp)) Directory.Delete(tmp, true); } catch (IOException) { }
            }
        }

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] static extern uint GetShortPathNameW(string longPath, StringBuilder shortPath, uint size);

        /// <summary>The simulators read paths with the ANSI code page, so a non-ASCII folder (a Persian or "ü" user name)
        /// turns into "?" for them: hand them the 8.3 short name of an existing folder instead.</summary>
        public static string AnsiSafe(string dir)
        {
            if (dir.All(c => c < 128)) return dir;
            var sb = new StringBuilder(1024);
            uint n = GetShortPathNameW(dir, sb, (uint)sb.Capacity);
            // shortcut: a volume without 8.3 names keeps the long path (simulator still breaks there; real fix routed in I-004)
            return n > 0 && n < sb.Capacity ? sb.ToString() : dir;
        }

        /// <summary>The running simulator of this build, found by its exe folder: waking from sleep restarts program.exe
        /// as a new process (on Windows execvp starts a new process and ends the old one), so the started handle is not enough.</summary>
        public static Process Running(Build b)
        {
            if (b == null) return null;
            var dir = BuildDir(b);
            Process found = null;
            foreach (var p in Process.GetProcessesByName("program"))
            {
                string d = null;
                try { d = Path.GetDirectoryName(p.MainModule.FileName); } catch (Exception) { } // exited or not ours
                if (found == null && d != null && (string.Equals(d, dir, StringComparison.OrdinalIgnoreCase)
                    || d.StartsWith(dir + "~old-", StringComparison.OrdinalIgnoreCase))) found = p; // ~old-: updated while it ran
                else p.Dispose();
            }
            return found;
        }

        /// <summary>Free books and an English dictionary (samples\ next to the app), copied once onto each SD card.
        /// Files already on the card are kept, so a reader's own dictionary choice (.crosspoint\dictionary.bin) stays.</summary>
        public static bool AddSamples(Build b)
        {
            var card = SdCard(b);
            var mark = Path.Combine(card, ".rsim-samples");
            if (File.Exists(mark) || !Directory.Exists(SamplesDir)) return false;
            foreach (var src in Directory.GetFiles(SamplesDir, "*", SearchOption.AllDirectories))
            {
                var dst = Path.Combine(card, src.Substring(SamplesDir.Length).TrimStart(Path.DirectorySeparatorChar));
                if (File.Exists(dst)) continue;
                Directory.CreateDirectory(Path.GetDirectoryName(dst));
                File.Copy(src, dst);
            }
            File.WriteAllText(mark, "sample books and dictionary added" + Environment.NewLine);
            return true;
        }

        public static Process Start(Build b, int battery, bool usb, IDictionary<string, string> extraEnv = null)
        {
            Directory.CreateDirectory(SdCard(b));
            try { AddSamples(b); } catch (Exception) { } // a full or read-only disk must not stop the simulator
            var psi = new ProcessStartInfo(Path.Combine(BuildDir(b), "program.exe"))
            {
                WorkingDirectory = AnsiSafe(CardDir(b)), UseShellExecute = false, CreateNoWindow = true,
                RedirectStandardOutput = true, RedirectStandardError = true,
            };
            if (b.Frame != null) psi.EnvironmentVariables["CROSSPOINT_SIM_FRAME"] = Path.Combine(AnsiSafe(FramesDir), b.Frame).Replace('\\', '/');
            psi.EnvironmentVariables["VARAGH_SIM_BATTERY"] = battery.ToString();
            psi.EnvironmentVariables["VARAGH_SIM_USB"] = usb ? "1" : "0";
            if (extraEnv != null) foreach (var kv in extraEnv) psi.EnvironmentVariables[kv.Key] = kv.Value;
            var log = TextWriter.Synchronized(new StreamWriter(Path.Combine(CardDir(b), "last-run.log"), false));
            var p = new Process { StartInfo = psi, EnableRaisingEvents = true };
            p.OutputDataReceived += (s, e) => { if (e.Data != null) log.WriteLine(e.Data); };
            p.ErrorDataReceived += (s, e) => { if (e.Data != null) log.WriteLine(e.Data); };
            p.Exited += (s, e) => { p.WaitForExit(); log.Dispose(); };
            p.Start();
            p.BeginOutputReadLine();
            p.BeginErrorReadLine();
            return p;
        }

        /// <summary>A frame's size and screen hole from its .keys file: { W, H, x, y, w, h }, or null.</summary>
        public static int[] FrameBox(string frame)
        {
            var box = new int[6];
            try
            {
                foreach (var line in File.ReadAllLines(Path.Combine(FramesDir, frame + ".keys")))
                {
                    var f = line.Split(' ');
                    if (f[0] == "size") { box[0] = int.Parse(f[1]); box[1] = int.Parse(f[2]); }
                    if (f[0] == "screen") for (int i = 0; i < 4; i++) box[2 + i] = int.Parse(f[1 + i]);
                }
            }
            catch (Exception) { return null; }
            return box[0] > 0 && box[4] > 0 ? box : null;
        }

        /// <summary>The installed package's build.json (source_commit, built), or an empty map.</summary>
        public static Dictionary<string, object> BuildInfo(Build b)
        {
            try { return new JavaScriptSerializer().DeserializeObject(File.ReadAllText(Path.Combine(BuildDir(b), "build.json"))) as Dictionary<string, object> ?? new Dictionary<string, object>(); }
            catch (Exception) { return new Dictionary<string, object>(); }
        }

        // settings.json: device, firmware repo, ref, battery, usb
        public static Dictionary<string, object> LoadSettings()
        {
            try { return new JavaScriptSerializer().DeserializeObject(File.ReadAllText(Path.Combine(Root, "settings.json"))) as Dictionary<string, object> ?? new Dictionary<string, object>(); }
            catch (Exception) { return new Dictionary<string, object>(); }
        }

        public static void SaveSettings(Dictionary<string, object> s)
        {
            try
            {
                // write a temp file, then swap it in: a power cut never leaves a half-written settings.json
                Directory.CreateDirectory(Root);
                string path = Path.Combine(Root, "settings.json"), tmp = path + ".tmp";
                File.WriteAllText(tmp, new JavaScriptSerializer().Serialize(s));
                if (File.Exists(path)) File.Replace(tmp, path, null); else File.Move(tmp, path);
            }
            catch (Exception) { }
        }
    }

    /// <summary>The running simulator's window: screenshots and touch gestures, as the web page does on its canvas.</summary>
    public static class ReaderWindow
    {
        struct RECT { public int Left, Top, Right, Bottom; }
        [DllImport("user32.dll")] static extern IntPtr SetThreadDpiAwarenessContext(IntPtr ctx);
        [DllImport("user32.dll")] static extern bool GetClientRect(IntPtr hwnd, out RECT r);
        [DllImport("user32.dll")] static extern bool PrintWindow(IntPtr hwnd, IntPtr hdc, uint flags);
        [DllImport("user32.dll")] static extern bool PostMessage(IntPtr hwnd, uint msg, IntPtr w, IntPtr l);

        // program.exe is not DPI-aware: measure, capture and click in its own unscaled pixels
        static T Unaware<T>(Func<T> f)
        {
            var old = SetThreadDpiAwarenessContext(new IntPtr(-1) /* DPI_AWARENESS_CONTEXT_UNAWARE */);
            try { return f(); } finally { SetThreadDpiAwarenessContext(old); }
        }

        static System.Drawing.Size ClientSize(IntPtr hwnd) =>
            Unaware(() => GetClientRect(hwnd, out var r) ? new System.Drawing.Size(r.Right, r.Bottom) : System.Drawing.Size.Empty);

        /// <summary>The screen hole in a window of width x height showing the whole frame. Same rule as the web page:
        /// when the window is turned (landscape), the hole is turned a quarter to the right.</summary>
        public static System.Drawing.RectangleF ScreenHole(string frame, int width, int height)
        {
            var k = frame == null ? null : Store.FrameBox(frame);
            if (k == null) return System.Drawing.RectangleF.Empty;
            int W = k[0], H = k[1], x = k[2], y = k[3], w = k[4], h = k[5];
            bool turned = (width > height) != (W > H);
            if (turned) { int t = W; W = H; H = t; int nx = k[1] - y - h, ny = x; x = nx; y = ny; t = w; w = h; h = t; }
            float sx = (float)width / W, sy = (float)height / H;
            return new System.Drawing.RectangleF(x * sx, y * sy, w * sx, h * sy);
        }

        /// <summary>Saves the window as a PNG, whole or only the screen hole. Works while it is covered by other windows.</summary>
        public static void Screenshot(IntPtr hwnd, string frame, bool screenOnly, string path)
        {
            var size = ClientSize(hwnd);
            if (size.Width <= 0 || size.Height <= 0) throw new InvalidOperationException("The simulator window has no size (is it minimised?).");
            using (var bmp = new System.Drawing.Bitmap(size.Width, size.Height))
            {
                using (var g = System.Drawing.Graphics.FromImage(bmp))
                {
                    var hdc = g.GetHdc();
                    try { if (!Unaware(() => PrintWindow(hwnd, hdc, 3 /* PW_CLIENTONLY | PW_RENDERFULLCONTENT */))) throw new InvalidOperationException("Windows could not copy the simulator window."); }
                    finally { g.ReleaseHdc(hdc); }
                }
                var crop = new System.Drawing.Rectangle(System.Drawing.Point.Empty, size);
                if (screenOnly) crop = System.Drawing.Rectangle.Intersect(crop, System.Drawing.Rectangle.Round(ScreenHole(frame, size.Width, size.Height)));
                using (var part = bmp.Clone(crop, bmp.PixelFormat)) part.Save(path, System.Drawing.Imaging.ImageFormat.Png);
            }
        }

        static void Mouse(IntPtr hwnd, uint msg, float x, float y) =>
            PostMessage(hwnd, msg, new IntPtr(msg == 0x202 ? 0 : 1 /* MK_LBUTTON */), new IntPtr(((int)y << 16) | ((int)x & 0xFFFF)));

        static async Task Drag(IntPtr hwnd, float x1, float y1, float x2, float y2, int ms)
        {
            Mouse(hwnd, 0x200 /* WM_MOUSEMOVE */, x1, y1);
            Mouse(hwnd, 0x201 /* WM_LBUTTONDOWN */, x1, y1);
            int steps = Math.Max(1, ms / 16);
            for (int i = 1; i <= steps; i++)
            {
                await Task.Delay(ms / steps);
                Mouse(hwnd, 0x200, x1 + (x2 - x1) * i / steps, y1 + (y2 - y1) * i / steps);
            }
            Mouse(hwnd, 0x202 /* WM_LBUTTONUP */, x2, y2);
        }

        /// <summary>A touch gesture on the screen: left, right, up, down (from the top) or hold. Same moves as the web page.</summary>
        public static Task Gesture(IntPtr hwnd, string frame, string g)
        {
            var size = ClientSize(hwnd);
            var r = ScreenHole(frame, size.Width, size.Height);
            if (r.IsEmpty) return Task.CompletedTask;
            float cx = r.Left + r.Width / 2, cy = r.Top + r.Height / 2, dx = r.Width * 0.3f, dy = r.Height * 0.3f;
            switch (g)
            {
                case "left": return Drag(hwnd, cx + dx, cy, cx - dx, cy, 250);
                case "right": return Drag(hwnd, cx - dx, cy, cx + dx, cy, 250);
                case "up": return Drag(hwnd, cx, cy + dy, cx, cy - dy, 250);
                case "down": return Drag(hwnd, cx, r.Top + 4, cx, r.Top + r.Height * 0.45f, 300);
                default: return Drag(hwnd, cx, cy, cx, cy, 900);
            }
        }
    }

    /// <summary>eink-qemu (github.com/serialx/eink-qemu, GPL-2.0): a real emulator that runs any firmware .bin.
    /// Its Windows app is downloaded and installed (per user, no admin) the first time someone runs their own firmware.</summary>
    public static class Emulator
    {
        // shortcut: pinned to one release so the download can be checked; bump all three when a newer eink-qemu is wanted
        const string Version = "0.8.1";
        const string SetupSha256 = "649037a2a6832dec9a43102742cf2e5b3e1724da01cceba82efc730da0ffecfc";
        public const long SetupBytes = 16112865;
        static readonly Uri SetupUrl = new Uri($"https://github.com/serialx/eink-qemu/releases/download/{Version}/eink-qemu-desktop-{Version}-x86_64-pc-windows-msvc-setup.exe");
        public const string Site = "https://serialx.github.io/eink-qemu/";

        static string Dir => Path.Combine(Path.GetDirectoryName(Store.Root), "eink-qemu"); // the installer's default folder
        public static string Cli => Path.Combine(Dir, "eink-qemu.exe");
        public static bool Installed => File.Exists(Cli);

        /// <summary>Downloads the pinned installer, refuses a SHA-256 mismatch, runs it and waits until it is closed.</summary>
        public static async Task Install(IProgress<long> progress, CancellationToken ct)
        {
            var setup = Path.Combine(Store.Root, "eink-qemu-setup.exe");
            try
            {
                var hash = await Feed.Download(SetupUrl, setup, SetupBytes, progress, ct);
                if (hash != SetupSha256) throw new InvalidDataException("The eink-qemu download is damaged or not the expected one (SHA-256 mismatch). Nothing was installed.");
                using (var p = Process.Start(new ProcessStartInfo(setup) { UseShellExecute = true }))
                    await Task.Run(() => p.WaitForExit());
            }
            finally { try { File.Delete(setup); } catch (IOException) { } }
            if (!Installed) throw new InvalidOperationException("The eink-qemu installer was closed before it finished, or it was installed in another folder (expected " + Dir + ").");
        }

        public static string Machine(string model) => model == "X4 Pro" ? "x4pro" : model == "X4 Classic" ? "x4" : "x3";

        static ProcessStartInfo Cli_(string args) => new ProcessStartInfo(Cli, args)
        {
            WorkingDirectory = Directory.CreateDirectory(Path.Combine(Store.Root, "emulator")).FullName, // its run folders go here
            UseShellExecute = false, CreateNoWindow = true,
        };

        static void CliWait(string args)
        {
            using (var p = Process.Start(Cli_(args)))
                if (!p.WaitForExit(120000) || p.ExitCode != 0) throw new InvalidOperationException("eink-qemu could not make the SD card (" + args.Split(' ')[1] + ").");
        }

        /// <summary>Opens the firmware in eink-qemu's window on the chosen reader. Each reader keeps one SD card image
        /// (emulator\x4pro.img and so on), made the first time with the same free books and dictionary as the simulator's cards.</summary>
        public static Process Run(string firmware, string model)
        {
            var card = Path.Combine(Store.Root, "emulator", Machine(model) + ".img");
            if (!File.Exists(card))
            {
                var tmp = card + ".new";
                if (File.Exists(tmp)) File.Delete(tmp);
                CliWait($"sd new \"{tmp}\"");
                // a folder is copied as itself, so hand over books\ and dictionaries\ rather than samples\
                var samples = Directory.Exists(Store.SamplesDir) ? Directory.GetDirectories(Store.SamplesDir) : new string[0];
                if (samples.Length > 0) CliWait($"sd put \"{tmp}\" " + string.Join(" ", samples.Select(d => "\"" + d + "\"")));
                File.Move(tmp, card);
            }
            // read its records ourselves: it stops when its output has nowhere to go
            var psi = Cli_($"run \"{firmware}\" --machine {Machine(model)} --sd \"{card}\" --sd-in-place --gui");
            psi.RedirectStandardOutput = psi.RedirectStandardError = true;
            var log = TextWriter.Synchronized(new StreamWriter(Path.Combine(Store.Root, "emulator", "last-run.log"), false));
            var p = new Process { StartInfo = psi, EnableRaisingEvents = true };
            p.OutputDataReceived += (s, e) => { if (e.Data != null) log.WriteLine(e.Data); };
            p.ErrorDataReceived += (s, e) => { if (e.Data != null) log.WriteLine(e.Data); };
            p.Exited += (s, e) => { p.WaitForExit(); log.Dispose(); };
            p.Start();
            p.BeginOutputReadLine();
            p.BeginErrorReadLine();
            return p;
        }
    }

    public static class Theme
    {
        public static bool Dark;

        public static bool SystemDark()
        {
            using (var k = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"))
                return k?.GetValue("AppsUseLightTheme") is int v && v == 0;
        }

        static Color Accent(bool dark)
        {
            // Windows 11 uses a lighter accent shade on dark and a darker one on light; AccentPalette holds 8 RGBA shades.
            using (var k = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Explorer\Accent"))
                if (k?.GetValue("AccentPalette") is byte[] p && p.Length >= 32)
                {
                    int i = (dark ? 1 : 4) * 4;
                    return Color.FromRgb(p[i], p[i + 1], p[i + 2]);
                }
            return dark ? Color.FromRgb(0x60, 0xCD, 0xFF) : Color.FromRgb(0x00, 0x5F, 0xB8);
        }

        public static void Apply(bool dark)
        {
            Dark = dark;
            var r = Application.Current.Resources;
            void Set(string key, uint argb) => r[key] = Freeze(Color.FromArgb((byte)(argb >> 24), (byte)(argb >> 16), (byte)(argb >> 8), (byte)argb));
            var a = Accent(dark);
            r["Accent"] = Freeze(a);
            r["AccentSoft"] = Freeze(Color.FromArgb(dark ? (byte)0x30 : (byte)0x1C, a.R, a.G, a.B));
            r["OnAccent"] = Freeze(Luminance(a) > 0.179 ? Colors.Black : Colors.White); // whichever contrasts more (WCAG), e.g. black on a yellow accent
            r["Link"] = Freeze(dark ? Color.FromRgb(0x99, 0xEB, 0xFF) : Color.FromRgb(0x00, 0x3E, 0x92)); // Windows 11 hyperlink colours
            if (dark)
            {
                Set("Bg", 0xFF202020); Set("Card", 0xFF2B2B2B); Set("CardStroke", 0xFF1D1D1D); Set("Text", 0xFFFFFFFF);
                Set("Text2", 0xFFA8A8A8); Set("Control", 0xFF373737); Set("ControlHover", 0xFF3E3E3E); Set("ControlPressed", 0xFF323232);
                Set("ControlStroke", 0xFF454545); Set("Track", 0xFF6E6E6E); Set("Subtle", 0x0FFFFFFF); Set("Stage", 0xFF3A3A3A);
            }
            else
            {
                Set("Bg", 0xFFF3F3F3); Set("Card", 0xFFFFFFFF); Set("CardStroke", 0xFFE5E5E5); Set("Text", 0xFF1B1B1B);
                Set("Text2", 0xFF616161); Set("Control", 0xFFFBFBFB); Set("ControlHover", 0xFFF5F5F5); Set("ControlPressed", 0xFFF0F0F0);
                Set("ControlStroke", 0xFFDDDDDD); Set("Track", 0xFF8A8A8A); Set("Subtle", 0x09000000); Set("Stage", 0xFFE9E9E9);
            }
        }

        static SolidColorBrush Freeze(Color c) { var b = new SolidColorBrush(c); b.Freeze(); return b; }

        static double Luminance(Color c)
        {
            double Lin(byte v) { double s = v / 255.0; return s <= 0.03928 ? s / 12.92 : Math.Pow((s + 0.055) / 1.055, 2.4); }
            return 0.2126 * Lin(c.R) + 0.7152 * Lin(c.G) + 0.0722 * Lin(c.B);
        }

        [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int value, int size);

        /// <summary>Dark title bar (Windows 10 20H1+ / 11) and, on Windows 11, a caption colour matching the window.</summary>
        public static void TitleBar(Window w)
        {
            var hwnd = new WindowInteropHelper(w).Handle;
            if (hwnd == IntPtr.Zero) return;
            int on = Dark ? 1 : 0;
            if (DwmSetWindowAttribute(hwnd, 20, ref on, 4) != 0) DwmSetWindowAttribute(hwnd, 19, ref on, 4);
            int caption = Dark ? 0x202020 : 0xF3F3F3; // COLORREF 0x00BBGGRR, grey so order does not matter
            DwmSetWindowAttribute(hwnd, 35, ref caption, 4);
        }
    }
}
