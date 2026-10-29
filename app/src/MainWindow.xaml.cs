using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Automation;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using Microsoft.Win32;

namespace ReaderSimulator
{
    public partial class MainWindow : Window
    {
        List<Build> builds = new List<Build>();
        string device = "X4 Pro", repo, gitRef;
        bool busy, loading, copying;
        System.Threading.CancellationTokenSource cancel; // set while a download runs
        bool shownRunning; // what the Start button shows; a timer refreshes when the simulator starts or ends (also after a wake)

        static Process Running(Build b) => Store.Running(b);

        [System.Runtime.InteropServices.DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr hwnd);
        [System.Runtime.InteropServices.DllImport("user32.dll")] static extern bool ShowWindowAsync(IntPtr hwnd, int cmd);
        [System.Runtime.InteropServices.DllImport("user32.dll")] static extern bool IsIconic(IntPtr hwnd);

        public static void BringToFront(IntPtr hwnd)
        {
            if (IsIconic(hwnd)) ShowWindowAsync(hwnd, 9 /* SW_RESTORE */);
            SetForegroundWindow(hwnd);
        }
        readonly Dictionary<string, object> settings = Store.LoadSettings();
        readonly Dictionary<string, BitmapImage> frames = new Dictionary<string, BitmapImage>();

        public MainWindow()
        {
            InitializeComponent();
            device = settings.TryGetValue("device", out var d) && Feed.Models.Contains(d as string) ? (string)d : "X4 Pro";
            repo = settings.TryGetValue("repo", out var r) ? r as string : null;
            gitRef = settings.TryGetValue("ref", out var g) ? g as string : null;
            loading = true;
            double bv = 80;
            try { if (settings.TryGetValue("battery", out var b)) bv = Convert.ToDouble(b, System.Globalization.CultureInfo.InvariantCulture); } catch (Exception) { }
            Battery.Value = double.IsNaN(bv) || double.IsInfinity(bv) ? 80 : bv; // the slider throws on NaN/Infinity
            Usb.IsChecked = settings.TryGetValue("usb", out var u) && u is bool ub && ub;
            RealSize.IsChecked = settings.TryGetValue("realSize", out var rs) && rs is bool rb && rb && PxPerMm > 0;
            loading = false;
            BatteryText.Text = (int)Battery.Value + " %";
            var ver = typeof(MainWindow).Assembly.GetName().Version;
            AboutTitle.Text = $"Reader Simulator {ver.Major}.{ver.Minor}.{ver.Build}";
            foreach (var m in Feed.Models)
            {
                var tile = new RadioButton { Style = (Style)FindResource("Tile"), Tag = m, GroupName = "device", Margin = new Thickness(0, 0, 8, 0) };
                AutomationProperties.SetName(tile, m);
                tile.Content = new StackPanel { Children = {
                    new TextBlock { Text = m, FontWeight = FontWeights.SemiBold },
                    new TextBlock { Style = (Style)FindResource("Caption"), Margin = new Thickness(0, 2, 0, 0) } } };
                tile.Checked += (s, e) => { device = (string)((RadioButton)s).Tag; Refresh(); };
                DevicePanel.Children.Add(tile);
            }
            foreach (RadioButton tb in ThemePanel.Children) tb.IsChecked = (string)tb.Tag == App.ThemeMode;
            SourceInitialized += (s, e) => Theme.TitleBar(this);
            SystemEvents.UserPreferenceChanged += OnThemeChanged;
            Closed += (s, e) => SystemEvents.UserPreferenceChanged -= OnThemeChanged;
            var poll = new System.Windows.Threading.DispatcherTimer { Interval = TimeSpan.FromSeconds(2) };
            poll.Tick += (s, e) => { if (!busy && !App.RenderOnly) using (var p = Running(Current)) if ((p != null) != shownRunning) Refresh(); };
            poll.Start();
            Closed += (s, e) => poll.Stop();
        }

        void OnThemeChanged(object s, UserPreferenceChangedEventArgs e)
        {
            if (e.Category != UserPreferenceCategory.General || App.ThemeMode != "system") return;
            Dispatcher.BeginInvoke(new Action(() => { Theme.Apply(Theme.SystemDark()); Theme.TitleBar(this); }));
        }

        // ---- feed -------------------------------------------------------------
        public async Task LoadFeed(Uri feed)
        {
            var cache = Path.Combine(Store.Root, "feed-cache.json");
            AboutFeed.Text = feed == null ? "No firmware list address is set in this copy of the app." : "Firmware list: " + feed;
            if (feed == null) { NoFeed.Text = "No firmware list is set in this copy of the app."; NoFeed.Visibility = Visibility.Visible; Populate(); return; }
            SetStatus("", "Reading the firmware list…");
            try
            {
                var json = await Feed.FetchText(feed);
                builds = Feed.Parse(json, feed);
                try { Directory.CreateDirectory(Store.Root); File.WriteAllText(cache, feed.AbsoluteUri + "\n" + json); } catch (IOException) { }
            }
            catch (Exception ex)
            {
                // Offline: use the last list we read from the same address, so downloaded builds still start.
                try
                {
                    var text = File.ReadAllText(cache);
                    int nl = text.IndexOf('\n');
                    if (text.Substring(0, nl) == feed.AbsoluteUri) builds = Feed.Parse(text.Substring(nl + 1), feed);
                }
                catch (Exception) { }
                NoFeed.Text = "Could not read the firmware list (" + ex.Message + ")." + (builds.Count > 0 ? " Showing the last list." : "");
                NoFeed.Visibility = Visibility.Visible;
            }
            builds.AddRange(await LoadEmu());
            Populate();
        }

        /// <summary>The firmwares that run in eink-qemu; the last list read when offline, none when there never was one.</summary>
        static async Task<List<Build>> LoadEmu()
        {
            var cache = Path.Combine(Store.Root, "emulator-cache.json");
            try
            {
                var json = await Feed.FetchText(Feed.EmuUrl);
                var list = Feed.ParseEmu(json);
                try { File.WriteAllText(cache, json); } catch (IOException) { }
                return list;
            }
            catch (Exception)
            {
                try { return Feed.ParseEmu(File.ReadAllText(cache)); } catch (Exception) { return new List<Build>(); }
            }
        }

        void Populate()
        {
            FillCredits();
            FirmwareList.Items.Clear();
            foreach (var g in builds.GroupBy(b => b.Repo ?? b.Name).OrderBy(g => FirstRank(g.Key))) // stable: the rest keep the feed's order
            {
                var first = g.First();
                var row = new Grid { Tag = g.Key };
                row.ColumnDefinitions.Add(new ColumnDefinition());
                row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
                row.Children.Add(new StackPanel { Children = {
                    new TextBlock { Text = first.Name, FontWeight = FontWeights.SemiBold, TextTrimming = TextTrimming.CharacterEllipsis },
                    new TextBlock { Text = (g.All(b => b.Emu) ? "eink-qemu  ·  " : "") + (first.Repo ?? "") + "  ·  " + Plural(g.Select(b => b.Ref).Distinct().Count(), "version"), Style = (Style)FindResource("Caption"),
                        TextWrapping = TextWrapping.NoWrap, TextTrimming = TextTrimming.CharacterEllipsis, ToolTip = first.Repo } } });
                // most firmwares run on every reader: only name the readers when some are missing
                var models = Feed.Models.Where(m => g.Any(b => b.Model == m)).ToList();
                if (models.Count < Feed.Models.Length)
                {
                    var chip = Chip(string.Join(", ", models) + " only");
                    chip.VerticalAlignment = VerticalAlignment.Center;
                    Grid.SetColumn(chip, 1);
                    row.Children.Add(chip);
                }
                var item = new ListBoxItem { Content = row, Tag = g.Key };
                AutomationProperties.SetName(item, first.Name);
                FirmwareList.Items.Add(item);
            }
            var pick = FirmwareList.Items.Cast<ListBoxItem>().FirstOrDefault(i => (string)i.Tag == repo) ?? FirmwareList.Items.Cast<ListBoxItem>().FirstOrDefault();
            if (pick != null) FirmwareList.SelectedItem = pick; else Refresh();
            if (builds.Count == 0 && NoFeed.Visibility != Visibility.Visible) { NoFeed.Text = "The firmware list is empty."; NoFeed.Visibility = Visibility.Visible; }
        }

        // Colours by resource reference, not FindResource: the Theme switch replaces the brushes, and these must follow it.
        static T Themed<T>(T e, params (DependencyProperty p, string key)[] refs) where T : FrameworkElement
        {
            foreach (var (p, key) in refs) e.SetResourceReference(p, key);
            return e;
        }

        Border Chip(string text) => Themed(new Border
        {
            BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(10), Padding = new Thickness(8, 2, 8, 2), Margin = new Thickness(8, 0, 0, 0),
            Child = Themed(new TextBlock { Text = text, FontSize = 11.5 }, (TextBlock.ForegroundProperty, "Text2")),
        }, (Border.BackgroundProperty, "Subtle"), (Border.BorderBrushProperty, "ControlStroke"));

        // The order every firmware list in the app uses: VARAGH, CrossPoint Reader, CrossInk, then the rest.
        static readonly string[] First = { "PewPewzxc/VARAGH", "crosspoint-reader/crosspoint-reader", "uxjulia/crossink" };
        static int FirstRank(string repo) { int i = Array.IndexOf(First, repo); return i < 0 ? First.Length : i; }

        static string Plural(int n, string w) => n + " " + w + (n == 1 ? "" : "s");

        void Firmware_Changed(object sender, SelectionChangedEventArgs e)
        {
            if (FirmwareList.SelectedItem is ListBoxItem item) repo = (string)item.Tag;
            VersionPanel.Children.Clear();
            var refs = builds.Where(b => (b.Repo ?? b.Name) == repo).Select(b => b.Ref).Distinct().ToList();
            if (!refs.Contains(gitRef)) gitRef = refs.FirstOrDefault();
            foreach (var r in refs)
            {
                var models = builds.Where(b => (b.Repo ?? b.Name) == repo && b.Ref == r).Select(b => b.Model);
                var chip = new RadioButton { Style = (Style)FindResource("Chip"), GroupName = "version", Tag = r,
                    Content = builds.First(b => (b.Repo ?? b.Name) == repo && b.Ref == r).Version, ToolTip = "Devices: " + string.Join(", ", models), IsChecked = r == gitRef };
                chip.Checked += (s, a) => { gitRef = (string)((RadioButton)s).Tag; Refresh(); };
                VersionPanel.Children.Add(chip);
            }
            Refresh();
        }

        Build Current => builds.FirstOrDefault(b => (b.Repo ?? b.Name) == repo && b.Ref == gitRef && b.Model == device);

        // ---- state ------------------------------------------------------------
        void Refresh()
        {
            foreach (RadioButton tile in DevicePanel.Children)
            {
                var m = (string)tile.Tag;
                if (tile.IsChecked != (m == device)) tile.IsChecked = m == device;
                var has = builds.Any(b => (b.Repo ?? b.Name) == repo && b.Ref == gitRef && b.Model == m);
                var cap = (TextBlock)((StackPanel)tile.Content).Children[1];
                cap.Text = repo == null ? "" : has ? "Available" : "Not in this version";
                tile.Opacity = repo == null || has ? 1 : 0.6;
            }
            var frame = Feed.Frames[Array.IndexOf(Feed.Models, device)];
            Preview.Source = FrameImage(frame);
            PlaceScreen(frame);
            var b = Current;
            PreviewTitle.Text = device;
            PreviewSub.Text = b != null ? b.Name + " " + b.Version : repo != null ? "This firmware version has no " + device + " build" : "Pick a firmware";
            bool emu = b?.Emu == true;
            bool ready = b != null && (emu ? Emulator.HasBin(b) : Store.Installed(b));
            var commit = ready && !emu && Store.BuildInfo(b).TryGetValue("source_commit", out var sc) && sc is string cs && cs.Length >= 7 ? " (" + cs.Substring(0, 7) + ")" : "";
            BuildInfo.Text = b == null ? "" : emu ? (b.Repo != null && b.Repo.Contains("/") ? "The author's own " : "Xteink's own ") + b.Ref + " file, unchanged · runs in eink-qemu's own window"
                : "Built from " + (b.Repo ?? b.Name) + " " + b.Ref + commit;
            using (var r = Running(b)) shownRunning = r != null;
            RunTools.IsEnabled = Gestures.IsEnabled = shownRunning;
            Gestures.Visibility = device == "X4 Pro" ? Visibility.Visible : Visibility.Collapsed; // the only reader with a touchscreen
            if (b?.Id != sdBuild) { sdBuild = b?.Id; sdDir = ""; }
            SdBox.IsEnabled = BtnZip.IsEnabled = b != null && !busy && !emu; // eink-qemu's window has its own SD card
            SdRender();
            StartText.Text = busy ? "Cancel download" : emu ? "Open in eink-qemu" : shownRunning ? "Show simulator" : ready ? "Start" : b != null ? "Download and start" : "Start";
            StartIcon.Text = busy ? "" : ready || b == null ? "" : "";
            BtnStart.IsEnabled = b != null || busy;
            BtnFolder.IsEnabled = BtnFresh.IsEnabled = b != null && !busy && !emu;
            BtnBooks.IsEnabled = b != null && !busy && !copying && !emu;
            if (!busy)
            {
                if (b == null) SetStatus("", repo == null ? "No firmware to show." : $"No {device} build of this version. Devices it has: " +
                    string.Join(", ", builds.Where(x => (x.Repo ?? x.Name) == repo && x.Ref == gitRef).Select(x => x.Model)) + ".");
                else if (emu) SetStatus(ready ? "" : "", (ready ? "Downloaded and checked." : $"Not downloaded yet ({Mb(b.Size)}): the author's file is downloaded and checked the first time.") +
                    " It opens in eink-qemu, a separate emulator, whose window has its own SD card, keys and touch.");
                else if (shownRunning) SetStatus("", $"{b.Name} {b.Version} is running on the {b.Model}. Close its window to stop it.");
                else if (ready) SetStatus("", "Downloaded and checked. Ready to start.");
                else SetStatus("", $"Not downloaded yet ({Mb(b.Size)}). It is downloaded and checked the first time you start it.");
                if (b != null && b.Frame == null) StatusText.Text += " This build shows the screen without the device frame.";
            }
            SaveSettings();
        }

        BitmapImage FrameImage(string frame)
        {
            if (frames.TryGetValue(frame, out var img)) return img;
            try
            {
                img = new BitmapImage();
                img.BeginInit();
                img.CacheOption = BitmapCacheOption.OnLoad;
                img.UriSource = new Uri(Path.Combine(Store.FramesDir, frame + ".png"));
                img.EndInit();
                img.Freeze();
            }
            catch (Exception) { img = null; }
            return frames[frame] = img;
        }

        /// <summary>Sizes the preview to the frame and puts the blank page under its screen (from the .keys file).</summary>
        void PlaceScreen(string frame)
        {
            var k = Store.FrameBox(frame);
            if (k == null) { PreviewScreen.Width = 0; return; }
            PreviewFrame.Width = k[0]; PreviewFrame.Height = k[1];
            PreviewScreen.Margin = new Thickness(k[2], k[3], 0, 0); PreviewScreen.Width = k[4]; PreviewScreen.Height = k[5];
        }

        static string Mb(long bytes) => bytes > 0 ? (bytes / 1048576.0).ToString("0.0") + " MB" : "size unknown";

        void SetStatus(string icon, string text) { StatusIcon.Text = icon; StatusText.Text = text; }

        void SaveSettings()
        {
            if (loading || App.RenderOnly) return;
            settings["device"] = device; settings["repo"] = repo; settings["ref"] = gitRef;
            settings["battery"] = (int)Battery.Value; settings["usb"] = Usb.IsChecked == true; settings["realSize"] = RealSize.IsChecked == true;
            Store.SaveSettings(settings);
        }

        // ---- actions ----------------------------------------------------------
        void Nav_Checked(object sender, RoutedEventArgs e)
        {
            if (SimPage == null) return;
            SimPage.Visibility = NavSim.IsChecked == true ? Visibility.Visible : Visibility.Collapsed;
            AboutPage.Visibility = NavAbout.IsChecked == true ? Visibility.Visible : Visibility.Collapsed;
        }

        void Theme_Checked(object sender, RoutedEventArgs e)
        {
            var mode = (string)((RadioButton)sender).Tag;
            if (loading || mode == App.ThemeMode) return;
            App.ThemeMode = mode;
            Theme.Apply(mode == "system" ? Theme.SystemDark() : mode == "dark");
            Theme.TitleBar(this);
            settings["theme"] = mode;
            SaveSettings();
        }

        // ---- Controls panel (F1) ------------------------------------------------
        IInputElement focusBeforeControls; // where focus goes back to when the panel closes

        public void ShowControls(bool show)
        {
            if (show) focusBeforeControls = Keyboard.FocusedElement;
            ControlsOverlay.Visibility = show ? Visibility.Visible : Visibility.Collapsed;
            if (show) BtnCloseControls.Focus();
            else if (!((focusBeforeControls as UIElement)?.Focus() ?? false) && SimPage.IsVisible) BtnControls.Focus();
        }

        void Controls_Click(object sender, RoutedEventArgs e) => ShowControls(true);
        void CloseControls_Click(object sender, RoutedEventArgs e) => ShowControls(false);

        void ControlsOverlay_MouseDown(object sender, MouseButtonEventArgs e)
        {
            if (!ControlsCard.IsMouseOver) ShowControls(false); // a click on the dimmed area, not on the panel
        }

        void Window_PreviewKeyDown(object sender, KeyEventArgs e)
        {
            if (e.Key == Key.F1) { ShowControls(ControlsOverlay.Visibility != Visibility.Visible); e.Handled = true; }
            else if (e.Key == Key.Escape && ControlsOverlay.Visibility == Visibility.Visible) { ShowControls(false); e.Handled = true; }
        }

        static readonly System.Text.RegularExpressions.Regex RepoRe = new System.Text.RegularExpressions.Regex(@"\A[A-Za-z0-9-]{1,39}/[A-Za-z0-9_.-]{1,100}\z");

        /// <summary>About: every firmware in the list, in the app's order: its name (a link to its GitHub project),
        /// its authors and its versions as chips.</summary>
        void FillCredits()
        {
            FirmwareCredits.Children.Clear();
            AboutStats.Inlines.Clear();
            foreach (var (n, what) in new[] { (builds.Select(b => b.Repo ?? b.Name).Distinct().Count(), "firmwares"),
                (builds.Select(b => (b.Repo ?? b.Name) + "@" + b.Ref).Distinct().Count(), "versions"), (builds.Select(b => b.Model).Distinct().Count(), "readers") })
            {
                if (AboutStats.Inlines.Count > 0) AboutStats.Inlines.Add(new System.Windows.Documents.Run("   ·   "));
                var num = new System.Windows.Documents.Run(n.ToString()) { FontWeight = FontWeights.SemiBold };
                num.SetResourceReference(System.Windows.Documents.TextElement.ForegroundProperty, "Text");
                AboutStats.Inlines.Add(num);
                AboutStats.Inlines.Add(new System.Windows.Documents.Run(" " + what));
            }
            bool firstRow = true;
            foreach (var g in builds.GroupBy(b => b.Repo ?? b.Name).OrderBy(g => FirstRank(g.Key)))
            {
                var first = g.First();
                bool hasRepo = first.Repo != null && RepoRe.IsMatch(first.Repo);
                var row = new StackPanel();
                row.Children.Add(new TextBlock { FontSize = 15, FontWeight = FontWeights.SemiBold, Text = first.Name, Margin = new Thickness(0, 0, 0, hasRepo ? 0 : 8) });
                if (hasRepo)
                    row.Children.Add(new TextBlock { Style = (Style)FindResource("Caption"), FontSize = 12.5, Margin = new Thickness(0, 4, 0, 8),
                        Text = $"by {first.Repo.Split('/')[0]} and contributors" });
                var chips = new WrapPanel();
                foreach (var v in g.Select(b => b.Version).Distinct())
                    chips.Children.Add(Themed(new Border
                    {
                        CornerRadius = new CornerRadius(9), Padding = new Thickness(8, 1, 8, 2),
                        Margin = new Thickness(0, 0, 8, 8), Child = new TextBlock { Text = v, FontSize = 12 },
                    }, (Border.BackgroundProperty, "AccentSoft")));
                row.Children.Add(chips);
                if (hasRepo)
                {
                    // like the website's Licence link: the licence is in the firmware's own repository
                    var link = new System.Windows.Documents.Hyperlink(new System.Windows.Documents.Run("Source code and licence →"))
                        { NavigateUri = new Uri("https://github.com/" + first.Repo) };
                    System.Windows.Automation.AutomationProperties.SetName(link, first.Name + ": source code and licence");
                    link.RequestNavigate += (s, e) =>
                    {
                        e.Handled = true;
                        try { Process.Start(new ProcessStartInfo(e.Uri.AbsoluteUri) { UseShellExecute = true }); }
                        catch (Exception ex) { MessageBox.Show(this, "Could not open the browser: " + ex.Message, "Reader Simulator"); }
                    };
                    row.Children.Add(new TextBlock { FontSize = 13, Margin = new Thickness(0, 0, 0, 8), Inlines = { link } });
                }
                FirmwareCredits.Children.Add(Themed(new Border
                {
                    BorderThickness = new Thickness(0, firstRow ? 0 : 1, 0, 0), Padding = new Thickness(0, 12, 0, 4), Child = row,
                }, (Border.BorderBrushProperty, "CardStroke")));
                firstRow = false;
            }
            if (builds.Count == 0)
                FirmwareCredits.Children.Add(new TextBlock { Style = (Style)FindResource("Caption"), Margin = new Thickness(0, 10, 0, 0),
                    Text = "The firmware list could not be read, so no firmware is shown." });
        }

        // Only these pages open: the links are fixed, not read from the feed.
        static readonly string[] Links = { "https://github.com/PewPewzxc", "https://www.linkedin.com/in/alireza-pakseresht-koubijari/",
            "https://github.com/PewPewzxc/reader-simulator", Emulator.Site, "https://buymeacoffee.com/pewpewzxc", "https://pewpewzxc.github.io/reader-simulator/",
            "https://github.com/uxjulia/crosspoint-simulator", "https://github.com/uxjulia/crossink-simulator", "https://www.libsdl.org/",
            "https://standardebooks.org/", "https://wordnet.princeton.edu/" };

        void Link_Click(object sender, RoutedEventArgs e)
        {
            var url = ((sender as FrameworkElement)?.Tag ?? (sender as FrameworkContentElement)?.Tag) as string; // buttons and hyperlinks
            if (Array.IndexOf(Links, url) < 0) return;
            try { Process.Start(new ProcessStartInfo(url) { UseShellExecute = true }); }
            catch (Exception ex) { MessageBox.Show(this, "Could not open the browser: " + ex.Message, "Reader Simulator"); }
        }

        void Battery_Changed(object sender, RoutedPropertyChangedEventArgs<double> e)
        {
            if (BatteryText == null) return;
            BatteryText.Text = (int)Battery.Value + " %";
            SaveSettings();
        }

        void Usb_Click(object sender, RoutedEventArgs e) => SaveSettings();

        async void Start_Click(object sender, RoutedEventArgs e)
        {
            if (busy) { cancel?.Cancel(); return; }
            var b = Current;
            if (b == null) return;
            if (b.Emu) { await StartEmu(b); return; }
            if (Running(b) is Process r)
            {
                r.Refresh();
                if (r.MainWindowHandle != IntPtr.Zero) BringToFront(r.MainWindowHandle);
                SetStatus("\uE946", $"{b.Name} {b.Version} on the {b.Model} is already running. Close its window to start it again.");
                return;
            }
            if (!Store.Installed(b))
            {
                busy = true; cancel = new System.Threading.CancellationTokenSource(); Refresh();
                Progress.Visibility = Visibility.Visible; Progress.Value = 0;
                try
                {
                    var p = new Progress<long>(n =>
                    {
                        Progress.Value = b.Size > 0 ? Math.Min(1, (double)n / b.Size) : 0;
                        SetStatus("", $"Downloading {b.Name} {b.Version} for {b.Model}… {Mb(n)} of {Mb(b.Size)}");
                    });
                    await Store.Install(b, p, cancel.Token);
                }
                catch (Exception ex)
                {
                    bool cancelled = cancel.IsCancellationRequested;
                    busy = false; cancel = null; Progress.Visibility = Visibility.Collapsed; Refresh();
                    SetStatus(cancelled ? "" : "", cancelled ? "Download cancelled. Nothing was installed." : "Download failed: " + ex.Message);
                    return;
                }
                busy = false; cancel = null; Progress.Visibility = Visibility.Collapsed; Refresh();
            }
            try
            {
                var scale = RealSize.IsChecked == true && b.Frame != null ? FrameScale(b.Frame) : 0;
                Store.Start(b, (int)Battery.Value, Usb.IsChecked == true, scale > 0
                    ? new Dictionary<string, string> { ["CROSSPOINT_SIM_SCALE"] = scale.ToString("0.0000", Invariant) } : null);
                Refresh();
                SetStatus("", $"Started {b.Name} {b.Version} on the {b.Model}. Battery {(int)Battery.Value} %, USB {(Usb.IsChecked == true ? "on" : "off")}.");
            }
            catch (Exception ex) { SetStatus("", "Could not start: " + ex.Message); }
        }

        void OpenCard_Click(object sender, RoutedEventArgs e)
        {
            var b = Current; if (b == null) return;
            Directory.CreateDirectory(Store.SdCard(b));
            Process.Start(new ProcessStartInfo("explorer.exe", "\"" + Store.SdCard(b) + "\"") { UseShellExecute = false });
        }

        void FreshCard_Click(object sender, RoutedEventArgs e)
        {
            var b = Current; if (b == null) return;
            var card = Store.SdCard(b);
            // it keeps its settings in memory and writes them back, so emptying under it would not stick
            using (var r = Running(b)) if (r != null) { SetStatus("\uE946", "Close the simulator window first, then make a fresh SD card."); return; }
            if (MessageBox.Show(this, $"Delete everything on the simulated SD card of {b.Name} {b.Version} ({b.Model})?\n\nBooks, settings and reading progress on it are removed. Your own files elsewhere are not touched.",
                    "Fresh SD card", MessageBoxButton.YesNo, MessageBoxImage.Warning, MessageBoxResult.No) != MessageBoxResult.Yes) return;
            try
            {
                if (Directory.Exists(card)) Directory.Delete(card, true);
                Directory.CreateDirectory(card);
                SetStatus("", "The SD card is empty again.");
            }
            catch (Exception ex) { SetStatus("", "Could not empty the SD card (is the simulator still running?): " + ex.Message); }
        }

        async void AddBooks_Click(object sender, RoutedEventArgs e)
        {
            var b = Current; if (b == null) return;
            var dlg = new OpenFileDialog { Title = "Add books to the simulated SD card", Multiselect = true,
                Filter = "Books (*.epub;*.txt;*.xtc;*.xtch;*.md)|*.epub;*.txt;*.xtc;*.xtch;*.md|All files (*.*)|*.*" };
            if (dlg.ShowDialog(this) != true) return;
            var books = Path.Combine(Store.SdCard(b), "books");
            Directory.CreateDirectory(books);
            var files = dlg.FileNames.ToList();
            int same = files.Count(f => File.Exists(Path.Combine(books, Path.GetFileName(f))));
            if (same > 0)
            {
                var answer = MessageBox.Show(this, $"{Plural(same, "book")} with the same name {(same == 1 ? "is" : "are")} already on the SD card.\n\nReplace {(same == 1 ? "it" : "them")}? (No keeps the ones on the card.)",
                    "Add books", MessageBoxButton.YesNoCancel, MessageBoxImage.Question, MessageBoxResult.No);
                if (answer == MessageBoxResult.Cancel) return;
                if (answer == MessageBoxResult.No) files.RemoveAll(f => File.Exists(Path.Combine(books, Path.GetFileName(f))));
            }
            int n = 0;
            copying = true; Refresh();
            try
            {
                foreach (var f in files)
                {
                    SetStatus("\uE896", $"Copying {Path.GetFileName(f)} ({n + 1} of {files.Count})…");
                    await Task.Run(() => File.Copy(f, Path.Combine(books, Path.GetFileName(f)), true)); // off the UI thread: big files, slow drives
                    n++;
                }
                copying = false; Refresh();
                SetStatus("", $"Copied {Plural(n, "book")} to the SD card.");
            }
            catch (Exception ex) { copying = false; Refresh(); SetStatus("", $"Copied {n}, then failed: " + ex.Message); }
        }

        // ---- running simulator: screenshots and touch gestures --------------------
        IntPtr ReaderHwnd(Build b)
        {
            using (var p = Running(b)) { if (p == null) return IntPtr.Zero; p.Refresh(); return p.MainWindowHandle; }
        }

        void Shot_Click(object sender, RoutedEventArgs e)
        {
            var b = Current; var hwnd = ReaderHwnd(b);
            if (hwnd == IntPtr.Zero) { SetStatus("", "Start the simulator first, then take the screenshot."); return; }
            bool screenOnly = (string)((FrameworkElement)sender).Tag == "screen";
            if (screenOnly && b.Frame == null) { SetStatus("", "This build has no frame, so the whole picture is the screen: use \"Whole reader\"."); return; }
            var dlg = new SaveFileDialog { Title = "Save screenshot", Filter = "PNG picture (*.png)|*.png",
                FileName = b.Id + (screenOnly ? "-screen-" : "-reader-") + DateTime.Now.ToString("yyyy-MM-dd-HH-mm-ss") + ".png",
                InitialDirectory = Environment.GetFolderPath(Environment.SpecialFolder.MyPictures) };
            if (dlg.ShowDialog(this) != true) return;
            try { ReaderWindow.Screenshot(hwnd, b.Frame, screenOnly, dlg.FileName); SetStatus("", "Saved " + Path.GetFileName(dlg.FileName) + "."); }
            catch (Exception ex) { SetStatus("", "Could not take the screenshot: " + ex.Message); }
        }

        async void Gesture_Click(object sender, RoutedEventArgs e)
        {
            var b = Current; var hwnd = ReaderHwnd(b);
            if (hwnd == IntPtr.Zero || b.Model != "X4 Pro") { SetStatus("", "Gestures need a running X4 Pro (the only reader with a touchscreen)."); return; }
            await ReaderWindow.Gesture(hwnd, b.Frame, (string)((FrameworkElement)sender).Tag);
        }

        // ---- real size --------------------------------------------------------
        // Real width of each frame in mm (size / px_per_mm in device-frames/frames/<model>.json).
        static readonly Dictionary<string, double> FrameMm = new Dictionary<string, double> { ["x3"] = 66.66, ["x4-classic"] = 72.05, ["x4-pro"] = 71.94 };
        const double CardW = 53.98, CardH = 85.6; // ID-1 card (bank card), held upright
        static readonly System.Globalization.CultureInfo Invariant = System.Globalization.CultureInfo.InvariantCulture;

        [System.Runtime.InteropServices.DllImport("user32.dll")] static extern IntPtr MonitorFromWindow(IntPtr hwnd, uint flags);
        [System.Runtime.InteropServices.DllImport("shcore.dll")] static extern int GetDpiForMonitor(IntPtr monitor, int type, out uint x, out uint y);

        /// <summary>App pixels per real mm on this screen, from Measure screen; 0 = not measured yet.</summary>
        double PxPerMm
        {
            get { try { return settings.TryGetValue("pxPerMm", out var v) ? Convert.ToDouble(v, Invariant) : 0; } catch (Exception) { return 0; } }
        }

        /// <summary>How much the simulator draws its frame bigger or smaller. program.exe is not DPI-aware, so
        /// Windows draws its pixels as app pixels (1/96 inch as Windows counts it), the unit Measure screen uses.</summary>
        double FrameScale(string frame)
        {
            var k = Store.FrameBox(frame);
            return k != null && FrameMm.TryGetValue(frame, out var mm) && PxPerMm > 0 ? mm * PxPerMm / k[0] : 0;
        }

        /// <summary>First guess for Measure screen: the monitor's own size (often missing or a little wrong).</summary>
        double MonitorPxPerMm()
        {
            try
            {
                var mon = MonitorFromWindow(new System.Windows.Interop.WindowInteropHelper(this).Handle, 2 /* nearest */);
                if (GetDpiForMonitor(mon, 2 /* raw */, out var raw, out _) == 0 && GetDpiForMonitor(mon, 0 /* effective */, out var eff, out _) == 0 && raw > 0 && eff > 0)
                    return raw / 25.4 * 96.0 / eff;
            }
            catch (Exception) { }
            return 96 / 25.4;
        }

        void RealSize_Click(object sender, RoutedEventArgs e)
        {
            if (RealSize.IsChecked == true && PxPerMm <= 0) Measure();
            SaveSettings();
            if (RealSize.IsChecked == true || shownRunning) SetStatus("", "The new size is used the next time you start the simulator.");
        }

        void Measure_Click(object sender, RoutedEventArgs e) => Measure();

        void Measure()
        {
            // the box can never be taller than the screen
            double max = Math.Max(3, Math.Min(9, (SystemParameters.WorkArea.Height - 260) / CardH));
            var slider = new Slider { Style = (Style)FindResource("FluentSlider"), Minimum = 2, Maximum = max, SmallChange = 0.01, LargeChange = 0.1,
                Width = 240, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(8, 0, 8, 0) };
            slider.Value = Math.Max(2, Math.Min(max, PxPerMm > 0 ? PxPerMm : MonitorPxPerMm()));
            // a drawn bank card with its real size written on it, as on the web page
            var chip = new Border { Background = (Brush)FindResource("Track"), Opacity = 0.5, CornerRadius = new CornerRadius(3),
                HorizontalAlignment = HorizontalAlignment.Left, VerticalAlignment = VerticalAlignment.Top };
            var box = new Border { BorderBrush = (Brush)FindResource("Accent"), BorderThickness = new Thickness(2),
                Background = (Brush)FindResource("Subtle"), HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Top,
                Child = new Grid { Children = { chip, new TextBlock { Style = (Style)FindResource("Caption"), TextAlignment = TextAlignment.Center,
                    HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center, Text = "Bank card\n85.6 × 54 mm" } } } };
            void ShowBox()
            {
                double s = slider.Value;
                box.Width = CardW * s; box.Height = CardH * s; box.CornerRadius = new CornerRadius(3.18 * s); // ID-1 corner radius
                chip.Width = 9 * s; chip.Height = 11 * s; chip.Margin = new Thickness(CardW * s / 2 - 4.5 * s, 12 * s, 0, 0);
            }
            slider.ValueChanged += (s, a) => ShowBox();
            ShowBox();
            Button Btn(string text) => new Button { Style = (Style)FindResource("Btn"), Content = text, MinWidth = 40 };
            var smaller = Btn("−"); smaller.Click += (s, a) => slider.Value -= 0.1;
            var bigger = Btn("+"); bigger.Click += (s, a) => slider.Value += 0.1;
            var done = new Button { Style = (Style)FindResource("AccentBtn"), Content = "Done", IsDefault = true, MinWidth = 90, Margin = new Thickness(0, 0, 8, 0) };
            var cancelBtn = Btn("Cancel"); cancelBtn.IsCancel = true; cancelBtn.MinWidth = 90;
            var dlg = Dialog("Measure your screen");
            done.Click += (s, a) => { dlg.DialogResult = true; };
            dlg.Content = new StackPanel
            {
                Margin = new Thickness(24), Width = Math.Max(420, CardW * max), Children = {
                    new TextBlock { Style = (Style)FindResource("Body"), Margin = new Thickness(0, 0, 0, 16), Text =
                        "Screens don't tell Windows exactly how big they really are, so this is needed once per screen. Hold a bank card (or any ID-size card) upright against the screen and make the box exactly as big as the card." },
                    new Grid { Height = CardH * max, Children = { box } },
                    new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Center, Margin = new Thickness(0, 16, 0, 20), Children = { smaller, slider, bigger } },
                    new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, Children = { done, cancelBtn } },
                },
            };
            if (dlg.ShowDialog() == true)
            {
                settings["pxPerMm"] = Math.Round(slider.Value, 3);
                RealSize.IsChecked = true;
                SetStatus("", "Screen measured. Real size is on; it is used the next time you start the simulator.");
            }
            else if (PxPerMm <= 0) RealSize.IsChecked = false;
            SaveSettings();
        }

        Window Dialog(string title)
        {
            var dlg = new Window
            {
                Title = title, Owner = this, SizeToContent = SizeToContent.WidthAndHeight, ResizeMode = ResizeMode.NoResize,
                WindowStartupLocation = WindowStartupLocation.CenterOwner, ShowInTaskbar = false, Background = (Brush)FindResource("Bg"),
                Foreground = (Brush)FindResource("Text"), FontFamily = (FontFamily)FindResource("UiFont"), FontSize = 14, UseLayoutRounding = true,
            };
            dlg.SourceInitialized += (s, a) => Theme.TitleBar(dlg);
            return dlg;
        }

        /// <summary>Asks for one line of text; null when cancelled.</summary>
        string Ask(string title, string text)
        {
            var dlg = Dialog(title);
            var input = new TextBox { Margin = new Thickness(0, 8, 0, 16), Padding = new Thickness(6, 4, 6, 4) };
            var ok = new Button { Style = (Style)FindResource("AccentBtn"), Content = "OK", IsDefault = true, MinWidth = 90, Margin = new Thickness(0, 0, 8, 0) };
            ok.Click += (s, a) => dlg.DialogResult = true;
            var no = new Button { Style = (Style)FindResource("Btn"), Content = "Cancel", IsCancel = true, MinWidth = 90 };
            dlg.Content = new StackPanel { Margin = new Thickness(24), Width = 360, Children = {
                new TextBlock { Style = (Style)FindResource("Body"), Text = text }, input,
                new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, Children = { ok, no } } } };
            dlg.Loaded += (s, a) => input.Focus();
            return dlg.ShowDialog() == true ? input.Text.Trim() : null;
        }

        // ---- SD card files ------------------------------------------------------
        string sdBuild, sdDir = ""; // sdDir: the open folder, relative to the card, "" = top

        string SdAbs(string rel) => Path.Combine(Store.SdCard(Current), rel.Replace('/', Path.DirectorySeparatorChar));

        void SdRender()
        {
            SdList.Items.Clear();
            var b = Current;
            SdPath.Text = b == null ? "" : "SD card /" + sdDir;
            SdEmpty.Text = b == null ? "Pick a firmware to see its SD card." : "";
            if (b == null) return;
            var dir = SdAbs(sdDir);
            if (!Directory.Exists(dir)) { if (sdDir != "") { sdDir = ""; SdRender(); } else SdEmpty.Text = "Start the firmware once to make its SD card."; return; }
            try
            {
                var entries = new DirectoryInfo(dir).GetFileSystemInfos()
                    .Where(i => !(sdDir == "" && i.Name == ".rsim-samples"))
                    .OrderBy(i => i is FileInfo).ThenBy(i => i.Name, StringComparer.OrdinalIgnoreCase);
                foreach (var i in entries)
                {
                    var row = new DockPanel();
                    var size = new TextBlock { Style = (Style)FindResource("Caption"), Text = i is FileInfo f ? Mb(f.Length) : "" };
                    DockPanel.SetDock(size, Dock.Right);
                    row.Children.Add(size);
                    row.Children.Add(new StackPanel { Orientation = Orientation.Horizontal, Children = {
                        new TextBlock { Style = (Style)FindResource("Icon"), FontSize = 14, Text = i is FileInfo ? "" : "", Margin = new Thickness(0, 0, 8, 0) },
                        new TextBlock { Text = i.Name, TextTrimming = TextTrimming.CharacterEllipsis } } });
                    var sdItem = new ListBoxItem { Content = row, Tag = (sdDir == "" ? "" : sdDir + "/") + i.Name };
                    AutomationProperties.SetName(sdItem, i.Name);
                    SdList.Items.Add(sdItem);
                }
            }
            catch (Exception ex) { SdPath.Text += "  (could not read: " + ex.Message + ")"; }
            if (SdList.Items.Count == 0) SdEmpty.Text = "This folder is empty.";
            if (SdList.Items.Count == 0) SdList.Items.Add(new ListBoxItem { IsEnabled = false, Content = new TextBlock { Style = (Style)FindResource("Caption"), Text = "This folder is empty." } });
        }

        string SdSelected => (SdList.SelectedItem as ListBoxItem)?.Tag as string;

        void SdList_DoubleClick(object sender, System.Windows.Input.MouseButtonEventArgs e)
        {
            var rel = SdSelected;
            if (rel == null) return;
            if (Directory.Exists(SdAbs(rel))) { sdDir = rel; SdRender(); }
            else try { Process.Start(new ProcessStartInfo("explorer.exe", "/select,\"" + SdAbs(rel) + "\"") { UseShellExecute = false }); } catch (Exception) { }
        }

        void SdUp_Click(object sender, RoutedEventArgs e)
        {
            int cut = sdDir.LastIndexOf('/');
            sdDir = cut < 0 ? "" : sdDir.Substring(0, cut);
            SdRender();
        }

        async Task SdCopy(IList<string> paths)
        {
            var dest = SdAbs(sdDir);
            Directory.CreateDirectory(dest);
            int n = 0;
            copying = true; Refresh();
            try
            {
                foreach (var src in paths)
                {
                    SetStatus("", $"Copying {Path.GetFileName(src)} ({n + 1} of {paths.Count})…");
                    await Task.Run(() =>
                    {
                        if (Directory.Exists(src)) CopyDir(src, Path.Combine(dest, Path.GetFileName(src)));
                        else File.Copy(src, Path.Combine(dest, Path.GetFileName(src)), true);
                    });
                    n++;
                }
                copying = false; Refresh();
                SetStatus("", $"Put {Plural(n, "item")} on the SD card in /{sdDir}.");
            }
            catch (Exception ex) { copying = false; Refresh(); SetStatus("", $"Copied {n}, then failed: " + ex.Message); }
        }

        static void CopyDir(string src, string dst)
        {
            Directory.CreateDirectory(dst);
            foreach (var f in Directory.GetFiles(src)) File.Copy(f, Path.Combine(dst, Path.GetFileName(f)), true);
            foreach (var d in Directory.GetDirectories(src)) CopyDir(d, Path.Combine(dst, Path.GetFileName(d)));
        }

        async void SdUpload_Click(object sender, RoutedEventArgs e)
        {
            var dlg = new OpenFileDialog { Title = "Upload files to /" + sdDir, Multiselect = true, Filter = "All files (*.*)|*.*" };
            if (dlg.ShowDialog(this) == true) await SdCopy(dlg.FileNames);
        }

        async void SdUploadDir_Click(object sender, RoutedEventArgs e)
        {
            string picked = null;
            using (var dlg = new System.Windows.Forms.FolderBrowserDialog { Description = "Upload a folder into /" + sdDir })
                if (dlg.ShowDialog() == System.Windows.Forms.DialogResult.OK) picked = dlg.SelectedPath;
            if (picked != null) await SdCopy(new[] { picked });
        }

        void SdNewDir_Click(object sender, RoutedEventArgs e)
        {
            var name = Ask("New folder", "Name of the new folder in /" + sdDir + ":");
            if (string.IsNullOrEmpty(name)) return;
            if (name == "." || name == ".." || name.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0) { SetStatus("", "That is not a valid folder name."); return; }
            try { Directory.CreateDirectory(SdAbs((sdDir == "" ? "" : sdDir + "/") + name)); SdRender(); }
            catch (Exception ex) { SetStatus("", "Could not make the folder: " + ex.Message); }
        }

        void SdSave_Click(object sender, RoutedEventArgs e)
        {
            var rel = SdSelected;
            if (rel == null || !File.Exists(SdAbs(rel))) { SetStatus("", "Select a file in the list first."); return; }
            var dlg = new SaveFileDialog { Title = "Save a copy", FileName = Path.GetFileName(rel), Filter = "All files (*.*)|*.*" };
            if (dlg.ShowDialog(this) != true) return;
            try { File.Copy(SdAbs(rel), dlg.FileName, true); SetStatus("", "Saved " + Path.GetFileName(dlg.FileName) + "."); }
            catch (Exception ex) { SetStatus("", "Could not save it: " + ex.Message); }
        }

        void SdDelete_Click(object sender, RoutedEventArgs e)
        {
            var rel = SdSelected;
            if (rel == null) { SetStatus("", "Select a file or folder in the list first."); return; }
            var abs = SdAbs(rel); bool dir = Directory.Exists(abs);
            if (MessageBox.Show(this, $"Delete /{rel}{(dir ? " and everything in it" : "")} from the simulated SD card?", "Delete",
                    MessageBoxButton.YesNo, MessageBoxImage.Warning, MessageBoxResult.No) != MessageBoxResult.Yes) return;
            try { if (dir) Directory.Delete(abs, true); else File.Delete(abs); SdRender(); SetStatus("", "Deleted /" + rel + "."); }
            catch (Exception ex) { SetStatus("", "Could not delete it: " + ex.Message); }
        }

        async void SdZip_Click(object sender, RoutedEventArgs e)
        {
            var b = Current; if (b == null) return;
            var dlg = new SaveFileDialog { Title = "Save the SD card as a zip file", Filter = "Zip file (*.zip)|*.zip", FileName = b.Id + "-sd-card.zip" };
            if (dlg.ShowDialog(this) != true) return;
            try
            {
                Directory.CreateDirectory(Store.SdCard(b));
                if (File.Exists(dlg.FileName)) File.Delete(dlg.FileName); // the dialog already asked to replace it
                await Task.Run(() => System.IO.Compression.ZipFile.CreateFromDirectory(Store.SdCard(b), dlg.FileName));
                SetStatus("", "Saved " + Path.GetFileName(dlg.FileName) + ".");
            }
            catch (Exception ex) { SetStatus("", "Could not save the zip: " + ex.Message); }
        }

        // ---- your own firmware (eink-qemu) ----------------------------------------
        async void OwnFirmware_Click(object sender, RoutedEventArgs e)
        {
            if (busy) return;
            var dlg = new OpenFileDialog { Title = $"Pick a firmware to run on the {device}", Filter = "Firmware (*.bin;*.xota)|*.bin;*.xota|All files (*.*)|*.*" };
            if (dlg.ShowDialog(this) != true) return;
            if (!await EnsureEmulator(Path.GetFileName(dlg.FileName), "Your own firmware", "Run my own firmware")) return;
            try
            {
                Emulator.Run(dlg.FileName, device);
                SetStatus("", $"Opened {Path.GetFileName(dlg.FileName)} on the {device} in eink-qemu. Its window has its own SD card, keys and touch.");
            }
            catch (Exception ex) { SetStatus("", "Could not start eink-qemu: " + ex.Message); }
        }

        /// <summary>Installs eink-qemu the first time (asks first); false when the person said no or it failed.</summary>
        async Task<bool> EnsureEmulator(string what, string who, string title)
        {
            if (Emulator.Installed) return true;
            if (MessageBox.Show(this, $"{who} runs in eink-qemu, a separate free emulator by serialx (GPL-2.0 licence). It is not installed yet.\n\n" +
                    $"1. Its Windows app ({Mb(Emulator.SetupBytes)}) is downloaded from github.com/serialx/eink-qemu and checked.\n" +
                    "2. Its installer opens: click through it. It installs for you only, without administrator rights.\n" +
                    $"3. {what} then opens on the {device} in eink-qemu's own window, with the free books and dictionary on its SD card.\n\nThis happens only the first time. Download eink-qemu now?",
                    title, MessageBoxButton.OKCancel, MessageBoxImage.Information, MessageBoxResult.OK) != MessageBoxResult.OK) return false;
            busy = true; cancel = new System.Threading.CancellationTokenSource(); Refresh();
            Progress.Visibility = Visibility.Visible; Progress.Value = 0;
            try
            {
                await Emulator.Install(new Progress<long>(n =>
                {
                    Progress.Value = Math.Min(1, (double)n / Emulator.SetupBytes);
                    SetStatus("", n < Emulator.SetupBytes ? $"Downloading eink-qemu… {Mb(n)} of {Mb(Emulator.SetupBytes)}" : "Finish the eink-qemu installer window to go on.");
                }), cancel.Token);
            }
            catch (Exception ex)
            {
                bool cancelled = cancel.IsCancellationRequested;
                busy = false; cancel = null; Progress.Visibility = Visibility.Collapsed; Refresh();
                SetStatus(cancelled ? "" : "", cancelled ? "Download cancelled. Nothing was installed." : ex.Message);
                return false;
            }
            busy = false; cancel = null; Progress.Visibility = Visibility.Collapsed; Refresh();
            return true;
        }

        /// <summary>A list entry that runs in eink-qemu: download the author's .bin once (checked), then open it.</summary>
        async Task StartEmu(Build b)
        {
            if (!await EnsureEmulator($"{b.Name} {b.Version}", b.Name, b.Name + " in eink-qemu")) return;
            if (!Emulator.HasBin(b))
            {
                busy = true; cancel = new System.Threading.CancellationTokenSource(); Refresh();
                Progress.Visibility = Visibility.Visible; Progress.Value = 0;
                try
                {
                    await Emulator.GetBin(b, new Progress<long>(n =>
                    {
                        Progress.Value = Math.Min(1, (double)n / b.Size);
                        SetStatus("", $"Downloading {b.Name} {b.Version} for {b.Model}… {Mb(n)} of {Mb(b.Size)}");
                    }), cancel.Token);
                }
                catch (Exception ex)
                {
                    bool cancelled = cancel.IsCancellationRequested;
                    busy = false; cancel = null; Progress.Visibility = Visibility.Collapsed; Refresh();
                    SetStatus(cancelled ? "" : "", cancelled ? "Download cancelled. Nothing was kept." : "Download failed: " + ex.Message);
                    return;
                }
                busy = false; cancel = null; Progress.Visibility = Visibility.Collapsed; Refresh();
            }
            try
            {
                Emulator.Run(Emulator.BinPath(b), b.Model, b.PowerHold);
                SetStatus("", $"Opened {b.Name} {b.Version} on the {b.Model} in eink-qemu. Its window has its own SD card, keys and touch.");
            }
            catch (Exception ex) { SetStatus("", "Could not start eink-qemu: " + ex.Message); }
        }
    }
}
