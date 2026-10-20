using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net.Http;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
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
        // Set at publish time to the https://github.com/<owner>/<repo>/releases/download/<tag>/index.json of the feed.
        public const string FEED_URL = "";
        public static readonly string[] Models = { "X4 Pro", "X4 Classic", "X3" };
        public static readonly string[] Frames = { "x4-pro", "x4-classic", "x3" };
        // No trailing dot/dash (Windows strips trailing dots) and no reserved device names (con, nul, com1...).
        static readonly Regex IdRe = new Regex("^[a-z0-9](?:[a-z0-9._-]{0,98}[a-z0-9])?$");
        static readonly Regex ReservedRe = new Regex(@"^(con|prn|aux|nul|com\d|lpt\d)(\.|$)");
        public static bool ValidId(string id) => id != null && IdRe.IsMatch(id) && !ReservedRe.IsMatch(id);
        public const int MaxFeedBytes = 4 << 20;
        public static TimeSpan StallTimeout = TimeSpan.FromSeconds(30);
        static readonly Regex HexRe = new Regex("^[0-9a-f]{64}$");
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
            var tmp = Path.Combine(Store.Root, "feed.download"); // one path for file: and https feeds, same 4 MB cap
            await Download(feed, tmp, MaxFeedBytes, null, CancellationToken.None);
            try { return File.ReadAllText(tmp); } finally { File.Delete(tmp); }
        }

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
                        Id = S("id"), Name = S("name"), Repo = S("repo"), Ref = S("ref"), Version = S("version") ?? S("ref"),
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
        public static string BuildDir(Build b) => Path.Combine(Root, "builds", b.Id);
        public static string CardDir(Build b) => Path.Combine(Root, "cards", b.Id);
        public static string SdCard(Build b) => Path.Combine(CardDir(b), "fs_");
        const string ShaFile = "installed.sha256"; // the zip's SHA-256, so a folder only counts for the feed entry it came from
        public const long MaxEntryBytes = 200L << 20;
        public static bool Installed(Build b)
        {
            try { return File.Exists(Path.Combine(BuildDir(b), "program.exe")) && File.ReadAllText(Path.Combine(BuildDir(b), ShaFile)).Trim() == b.Sha256; }
            catch (IOException) { return false; }
        }

        /// <summary>Download, refuse a SHA-256 mismatch, unpack only the listed files.</summary>
        public static async Task Install(Build b, IProgress<long> progress, CancellationToken ct)
        {
            var builds = Path.Combine(Root, "builds");
            Directory.CreateDirectory(builds);
            var zip = Path.Combine(builds, b.Id + ".zip.part");
            var tmp = Path.Combine(builds, b.Id + ".unpacking");
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
                if (Directory.Exists(BuildDir(b))) Directory.Delete(BuildDir(b), true);
                Directory.Move(tmp, BuildDir(b));
            }
            finally
            {
                try { File.Delete(zip); if (Directory.Exists(tmp)) Directory.Delete(tmp, true); } catch (IOException) { }
            }
        }

        public static Process Start(Build b, int battery, bool usb, IDictionary<string, string> extraEnv = null)
        {
            Directory.CreateDirectory(SdCard(b));
            var psi = new ProcessStartInfo(Path.Combine(BuildDir(b), "program.exe"))
            {
                WorkingDirectory = CardDir(b), UseShellExecute = false, CreateNoWindow = true,
                RedirectStandardOutput = true, RedirectStandardError = true,
            };
            if (b.Frame != null) psi.EnvironmentVariables["CROSSPOINT_SIM_FRAME"] = Path.Combine(FramesDir, b.Frame).Replace('\\', '/');
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

        // settings.json: device, firmware repo, ref, battery, usb
        public static Dictionary<string, object> LoadSettings()
        {
            try { return (Dictionary<string, object>)new JavaScriptSerializer().DeserializeObject(File.ReadAllText(Path.Combine(Root, "settings.json"))); }
            catch (Exception) { return new Dictionary<string, object>(); }
        }

        public static void SaveSettings(Dictionary<string, object> s)
        {
            try { Directory.CreateDirectory(Root); File.WriteAllText(Path.Combine(Root, "settings.json"), new JavaScriptSerializer().Serialize(s)); }
            catch (Exception) { }
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
            r["OnAccent"] = Freeze(dark ? Colors.Black : Colors.White);
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
