using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.IO.Compression;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;

namespace ReaderSimulator
{
    sealed class StallStream : MemoryStream
    {
        public override Task<int> ReadAsync(byte[] b, int o, int c, CancellationToken t) => new TaskCompletionSource<int>().Task;
    }

    public partial class App : Application
    {
        public static bool? ForcedTheme; // --theme light|dark
        public static bool RenderOnly;
        static Mutex instance; // held for the app's lifetime

        [DllImport("kernel32.dll")] static extern bool AttachConsole(int pid);

        static string Arg(string[] a, string name) { int i = Array.IndexOf(a, name); return i >= 0 && i + 1 < a.Length ? a[i + 1] : null; }

        protected override async void OnStartup(StartupEventArgs e)
        {
            var a = e.Args;
            var theme = Arg(a, "--theme");
            if (theme != null) ForcedTheme = theme == "dark";
            Theme.Apply(ForcedTheme ?? Theme.SystemDark());
            var feedArg = Arg(a, "--feed");
            Uri feed = null;
            try { feed = feedArg != null ? Feed.ToUri(feedArg) : Feed.FEED_URL != "" ? new Uri(Feed.FEED_URL) : null; }
            catch (Exception) { }

            if (a.Contains("--selftest"))
            {
                ShutdownMode = ShutdownMode.OnExplicitShutdown;
                AttachConsole(-1);
                int code;
                try { code = await SelfTest(feed); }
                catch (Exception ex) { Log("FAIL " + ex.Message); code = 1; }
                Shutdown(code);
                return;
            }

            var w = new MainWindow();
            var render = Arg(a, "--render-ui");
            if (render != null)
            {
                RenderOnly = true;
                ShutdownMode = ShutdownMode.OnExplicitShutdown;
                if (Arg(a, "--page") == "about") w.NavAbout.IsChecked = true;
                await w.LoadFeed(feed);
                Shutdown(RenderUi(w, Path.GetFullPath(render)) ? 0 : 1);
                return;
            }
            // One window per data folder: a second start brings the first window forward (they would share settings and cards).
            instance = new Mutex(true, @"Local\ReaderSimulator:" + Store.Root.ToLowerInvariant().Replace('\\', '/'), out bool first);
            if (!first)
            {
                var me = System.Diagnostics.Process.GetCurrentProcess();
                foreach (var other in System.Diagnostics.Process.GetProcessesByName(me.ProcessName).Where(o => o.Id != me.Id && o.MainWindowHandle != IntPtr.Zero))
                    ReaderSimulator.MainWindow.BringToFront(other.MainWindowHandle);
                Shutdown(0);
                return;
            }
            MainWindow = w;
            w.Show();
            await w.LoadFeed(feed);
        }

        /// <summary>Lays the window content out at 1160x780 and saves it at 2x (192 dpi), without showing anything.</summary>
        static bool RenderUi(MainWindow w, string png)
        {
            var root = w.Root;
            w.Content = null; // render the content tree on its own: a Window cannot be laid out unshown
            var host = new System.Windows.Controls.Border { Child = root, Width = w.Width, Height = w.Height, Background = (Brush)Current.Resources["Bg"] };
            host.Measure(new Size(w.Width, w.Height));
            host.Arrange(new Rect(0, 0, w.Width, w.Height));
            host.UpdateLayout();
            host.Dispatcher.Invoke(() => { }, System.Windows.Threading.DispatcherPriority.Render);
            var bmp = new RenderTargetBitmap((int)(w.Width * 2), (int)(w.Height * 2), 192, 192, PixelFormats.Pbgra32);
            bmp.Render(host);
            var enc = new PngBitmapEncoder();
            enc.Frames.Add(BitmapFrame.Create(bmp));
            Directory.CreateDirectory(Path.GetDirectoryName(png));
            using (var f = File.Create(png)) enc.Save(f);
            return true;
        }

        static void Log(string s)
        {
            Console.WriteLine(s);
            try { Directory.CreateDirectory(Store.Root); File.AppendAllText(Path.Combine(Store.Root, "selftest.log"), DateTime.Now.ToString("s") + " " + s + Environment.NewLine); }
            catch (IOException) { }
        }

        /// <summary>Checks the safety rules, then downloads, verifies, unpacks and runs the first build headless.</summary>
        static async Task<int> SelfTest(Uri feed)
        {
            bool ok(string u, bool file) => Feed.Allowed(new Uri(u), file);
            if (!(ok("https://github.com/a/b/releases/download/t/x.zip", false) && ok("https://objects.githubusercontent.com/x", false)
                  && !ok("http://github.com/a", false) && !ok("https://evil.example/x.zip", false) && !ok("https://github.com.evil.example/x", false)
                  && !ok("https://github.com:8443/x", false) && !ok("https://u:p@github.com/x", false)
                  && !ok("file:///C:/x.zip", false) && ok("file:///C:/x.zip", true) && !ok(@"file://server/share/x.zip", true)))
                throw new Exception("address allow-list check failed");
            var badId = Feed.Parse("{\"schema\":1,\"builds\":[{\"id\":\"..\\\\x\",\"name\":\"a\",\"ref\":\"1\",\"model\":\"X3\",\"sha256\":\"" + new string('0', 64) + "\",\"url\":\"https://github.com/x\"}]}", new Uri("https://github.com/f/index.json"));
            if (badId.Count != 0) throw new Exception("feed validation let a bad id through");
            foreach (var id in new[] { "abc.", "abc-", ".abc", "con", "nul.zip", "com1", "lpt9.x", "aux", "a/b", "A", "abc\n", "a~old" })
                if (Feed.ValidId(id)) throw new Exception("id check accepted " + id.Replace("\n", "\\n"));
            foreach (var id in new[] { "a", "pewpewzxc-varagh-1.3.0-x4-pro", "console", "com1-x" })
                if (!Feed.ValidId(id)) throw new Exception("id check refused " + id);
            var nlSha = Feed.Parse("{\"schema\":1,\"builds\":[{\"id\":\"a\",\"name\":\"a\",\"ref\":\"1\",\"model\":\"X3\",\"sha256\":\"" + new string('0', 64) + "\\n\",\"url\":\"https://github.com/x\"}]}", new Uri("https://github.com/f/index.json"));
            if (nlSha.Count != 0) throw new Exception("feed validation let a sha256 ending in a newline through");
            if (Store.Installed(new Build { Id = "a\0b", Sha256 = new string('0', 64) })) throw new Exception("bad path counted as installed");
            Log("allow-list and feed validation: ok");

            // a damaged settings.json must not stop the window from opening (I-002)
            var settingsFile = Path.Combine(Store.Root, "settings.json");
            Directory.CreateDirectory(Store.Root);
            foreach (var s in new[] { "", "{\"battery\":\"high\"}", "{\"battery\":[1]}", "{\"battery\":\"Infinity\"}", "[1,2]" })
            {
                File.WriteAllText(settingsFile, s);
                new MainWindow().Close();
            }
            File.Delete(settingsFile);
            Store.SaveSettings(new Dictionary<string, object> { ["battery"] = 42 });
            Store.SaveSettings(new Dictionary<string, object> { ["battery"] = 43 }); // the second save replaces an existing file
            if (Convert.ToInt32(Store.LoadSettings()["battery"]) != 43 || File.Exists(settingsFile + ".tmp")) throw new Exception("settings save/replace failed");
            File.Delete(settingsFile);
            Log("damaged settings.json: ok");

            // a download into a folder that does not exist yet (first run with an https feed used to fail here)
            var fresh = Path.Combine(Store.Root, "selftest-" + Guid.NewGuid().ToString("N"), "sub");
            File.WriteAllText(Path.Combine(Path.GetTempPath(), "rsim-selftest.txt"), "x");
            await Feed.Download(new Uri(Path.Combine(Path.GetTempPath(), "rsim-selftest.txt")), Path.Combine(fresh, "feed.download"), 10, null, CancellationToken.None);
            Directory.Delete(Path.GetDirectoryName(fresh), true);
            // a stream that never sends data must stop after the stall timeout, and Cancel must stop it at once
            var keep = Feed.StallTimeout;
            Feed.StallTimeout = TimeSpan.FromSeconds(1);
            try { await Feed.ReadOrStall(new StallStream(), new byte[16], CancellationToken.None); throw new Exception("stalled read did not time out"); }
            catch (TimeoutException) { }
            Feed.StallTimeout = keep;
            using (var cts = new CancellationTokenSource(200))
                try { await Feed.ReadOrStall(new StallStream(), new byte[16], cts.Token); throw new Exception("cancel did not stop the read"); }
                catch (OperationCanceledException) { }
            // a zip entry over 200 MB is refused (zeros compress to a small file)
            var bomb = Path.Combine(Store.Root, "selftest-big.zip");
            Directory.CreateDirectory(Store.Root);
            using (var z = ZipFile.Open(bomb, ZipArchiveMode.Create))
            using (var w = z.CreateEntry("program.exe").Open())
            {
                var zeros = new byte[1 << 20];
                for (int i = 0; i < 201; i++) w.Write(zeros, 0, zeros.Length);
            }
            var big = new Build { Id = "selftest-big", Url = new Uri(bomb), Sha256 = await Feed.Download(new Uri(bomb), bomb + ".copy", 0, null, CancellationToken.None) };
            File.Delete(bomb + ".copy");
            try { await Store.Install(big, null, CancellationToken.None); throw new Exception("a 201 MB zip entry was accepted"); }
            catch (InvalidDataException) { }
            File.Delete(bomb);
            if (Directory.Exists(Store.BuildDir(big))) throw new Exception("oversized entry left files");
            Log("fresh folder, stall timeout, cancel, 200 MB entry cap: ok");

            if (feed == null) throw new Exception("no feed (use --feed)");
            var builds = Feed.Parse(await Feed.FetchText(feed), feed);
            Log($"feed {feed}: {builds.Count} builds");
            // two windows reading the feed at the same moment (I-007), and no temp file left behind
            await Task.WhenAll(Feed.FetchText(feed), Feed.FetchText(feed), Feed.FetchText(feed));
            if (Directory.GetFiles(Store.Root, "feed*.download").Any()) throw new Exception("feed temp file left behind");
            Log("parallel feed reads: ok");
            var b = builds.FirstOrDefault() ?? throw new Exception("feed has no builds");

            var wrong = new Build { Id = b.Id + "-shacheck", Url = b.Url, Size = b.Size, Sha256 = new string('0', 64) };
            try { await Store.Install(wrong, null, CancellationToken.None); throw new Exception("a SHA-256 mismatch was accepted"); }
            catch (InvalidDataException) { }
            if (Directory.Exists(Store.BuildDir(wrong))) throw new Exception("mismatched download left files");
            Log("SHA-256 mismatch refused: ok");

            if (Directory.Exists(Store.BuildDir(b))) Directory.Delete(Store.BuildDir(b), true);
            var t = DateTime.Now;
            await Store.Install(b, null, CancellationToken.None);
            var files = Directory.GetFiles(Store.BuildDir(b)).Select(Path.GetFileName).ToArray();
            if (files.Except(Store.PackageFiles).Except(new[] { "installed.sha256" }).Any()) throw new Exception("unpacked an unlisted file");
            if (!Store.Installed(b)) throw new Exception("installed build not recognised");
            if (Store.Installed(new Build { Id = b.Id, Sha256 = new string('1', 64) })) throw new Exception("build folder trusted for a different SHA-256");
            Log($"installed {b.Id} in {(DateTime.Now - t).TotalSeconds:0.0} s: {string.Join(", ", files)}");

            var shot = Path.Combine(Store.CardDir(b), "selftest.bmp");
            if (File.Exists(shot)) File.Delete(shot);
            var p = Store.Start(b, 55, true, new Dictionary<string, string>
            {
                ["SDL_VIDEODRIVER"] = "dummy", ["SDL_RENDER_DRIVER"] = "software", ["SDL_AUDIODRIVER"] = "dummy",
                ["CROSSPOINT_SIM_INPUT_SCRIPT"] = "6000:QUIT", ["CROSSPOINT_SIM_SCREENSHOTS"] = "4000:selftest.bmp", // relative: the simulator splits on ':'
            });
            // the simulators read paths with the ANSI code page: what they get must be plain ASCII (I-004, I-005)
            if (p.StartInfo.WorkingDirectory.Any(c => c > 127) || (b.Frame != null && p.StartInfo.EnvironmentVariables["CROSSPOINT_SIM_FRAME"].Any(c => c > 127)))
                throw new Exception("the simulator was given a non-ASCII path (no 8.3 short names on this drive?)");
            // updating a build while its simulator runs must replace it cleanly (I-003)
            await Task.Delay(1500);
            if (p.HasExited) throw new Exception("simulator quit too early for the running-update check");
            await Store.Install(b, null, CancellationToken.None);
            if (!Store.Installed(b)) throw new Exception("update while running broke the build");
            Log("update while the simulator runs: ok");
            if (!await Task.Run(() => p.WaitForExit(90000))) { p.Kill(); throw new Exception("simulator did not quit within 90 s"); }
            Log($"simulator exit code {p.ExitCode}; screenshot {(File.Exists(shot) ? new FileInfo(shot).Length + " bytes at " + shot : "MISSING")}");
            if (b.Frame != null && File.Exists(shot))
            {
                var hdr = new byte[22];
                using (var f = File.OpenRead(shot)) f.Read(hdr, 0, hdr.Length);
                var size = File.ReadAllLines(Path.Combine(Store.FramesDir, b.Frame + ".keys")).First(l => l.StartsWith("size ")).Split(' ');
                if (BitConverter.ToInt32(hdr, 18) != int.Parse(size[1])) throw new Exception($"screenshot is {BitConverter.ToInt32(hdr, 18)} px wide, the {b.Frame} frame {size[1]}: the frame was not drawn");
                Log("device frame drawn: ok");
            }

            // Sleep and wake: the simulator restarts as a new process (I-011); the app must still see it running.
            p = Store.Start(b, 55, true, new Dictionary<string, string>
            {
                ["SDL_VIDEODRIVER"] = "dummy", ["SDL_RENDER_DRIVER"] = "software", ["SDL_AUDIODRIVER"] = "dummy",
                ["CROSSPOINT_SIM_INPUT_SCRIPT"] = "1500:SLEEP;3000:POWER;12000:QUIT", ["CROSSPOINT_SIM_INPUT_SCRIPT_AFTER_WAKE"] = "2500:QUIT",
            });
            // (WaitForExit on the first process can wait for the pipes the woken one inherited, so poll instead)
            Process woke = null;
            for (int i = 0, gone = 0; i < 300 && woke == null && gone < 30; i++) // gone: 3 s after the first process ended
            {
                await Task.Delay(100);
                var r = Store.Running(b);
                if (r != null && r.Id != p.Id) woke = r;
                else { r?.Dispose(); if (p.HasExited) gone++; }
            }
            if (woke == null && !p.HasExited) { p.Kill(); throw new Exception("simulator did not quit within 30 s"); }
            if (woke == null) Log("sleep/wake: no restart seen (this simulator has no SLEEP script key?), skipped");
            else
            {
                if (!p.HasExited) await Task.Delay(2000);
                if (!p.HasExited) throw new Exception("old process still running after the wake");
                if (Store.Running(b) == null && !woke.HasExited) throw new Exception("woken simulator not seen as running");
                if (!await Task.Run(() => woke.WaitForExit(30000))) { woke.Kill(); throw new Exception("woken simulator did not quit"); }
                Log("sleep/wake restart seen as still running: ok");
            }
            return File.Exists(shot) ? 0 : 1;
        }
    }
}
