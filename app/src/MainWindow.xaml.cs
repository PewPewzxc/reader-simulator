using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using Microsoft.Win32;

namespace ReaderSimulator
{
    public partial class MainWindow : Window
    {
        List<Build> builds = new List<Build>();
        string device = "X4 Pro", repo, gitRef;
        bool busy, loading;
        System.Threading.CancellationTokenSource cancel; // set while a download runs
        readonly Dictionary<string, object> settings = Store.LoadSettings();
        readonly Dictionary<string, BitmapImage> frames = new Dictionary<string, BitmapImage>();

        public MainWindow()
        {
            InitializeComponent();
            device = settings.TryGetValue("device", out var d) && Feed.Models.Contains(d as string) ? (string)d : "X4 Pro";
            repo = settings.TryGetValue("repo", out var r) ? r as string : null;
            gitRef = settings.TryGetValue("ref", out var g) ? g as string : null;
            loading = true;
            Battery.Value = settings.TryGetValue("battery", out var b) ? Convert.ToDouble(b) : 80;
            Usb.IsChecked = settings.TryGetValue("usb", out var u) && u is bool ub && ub;
            loading = false;
            BatteryText.Text = (int)Battery.Value + " %";
            var ver = typeof(MainWindow).Assembly.GetName().Version;
            AboutTitle.Text = $"Reader Simulator {ver.Major}.{ver.Minor}.{ver.Build}";
            foreach (var m in Feed.Models)
            {
                var tile = new RadioButton { Style = (Style)FindResource("Tile"), Tag = m, GroupName = "device", Margin = new Thickness(0, 0, m == "X3" ? 0 : 8, 0) };
                tile.Content = new StackPanel { Children = {
                    new TextBlock { Text = m, FontWeight = FontWeights.SemiBold },
                    new TextBlock { Style = (Style)FindResource("Caption"), Margin = new Thickness(0, 2, 0, 0) } } };
                tile.Checked += (s, e) => { device = (string)((RadioButton)s).Tag; Refresh(); };
                DevicePanel.Children.Add(tile);
            }
            SourceInitialized += (s, e) => Theme.TitleBar(this);
            SystemEvents.UserPreferenceChanged += OnThemeChanged;
            Closed += (s, e) => SystemEvents.UserPreferenceChanged -= OnThemeChanged;
        }

        void OnThemeChanged(object s, UserPreferenceChangedEventArgs e)
        {
            if (e.Category != UserPreferenceCategory.General || App.ForcedTheme != null) return;
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
            Populate();
        }

        void Populate()
        {
            FirmwareList.Items.Clear();
            foreach (var g in builds.GroupBy(b => b.Repo ?? b.Name).OrderBy(g => g.First().Name, StringComparer.OrdinalIgnoreCase))
            {
                var first = g.First();
                var row = new Grid { Tag = g.Key };
                row.ColumnDefinitions.Add(new ColumnDefinition());
                row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
                row.Children.Add(new StackPanel { Children = {
                    new TextBlock { Text = first.Name, FontWeight = FontWeights.SemiBold },
                    new TextBlock { Text = (first.Repo ?? "") + "  ·  " + Plural(g.Select(b => b.Ref).Distinct().Count(), "version"), Style = (Style)FindResource("Caption") } } });
                var chips = new StackPanel { Orientation = Orientation.Horizontal, VerticalAlignment = VerticalAlignment.Center };
                foreach (var m in Feed.Models.Where(m => g.Any(b => b.Model == m))) chips.Children.Add(Chip(m));
                Grid.SetColumn(chips, 1);
                row.Children.Add(chips);
                FirmwareList.Items.Add(new ListBoxItem { Content = row, Tag = g.Key });
            }
            var pick = FirmwareList.Items.Cast<ListBoxItem>().FirstOrDefault(i => (string)i.Tag == repo) ?? FirmwareList.Items.Cast<ListBoxItem>().FirstOrDefault();
            if (pick != null) FirmwareList.SelectedItem = pick; else Refresh();
            if (builds.Count == 0 && NoFeed.Visibility != Visibility.Visible) { NoFeed.Text = "The firmware list is empty."; NoFeed.Visibility = Visibility.Visible; }
        }

        Border Chip(string text) => new Border
        {
            Background = (Brush)FindResource("Subtle"), BorderBrush = (Brush)FindResource("ControlStroke"), BorderThickness = new Thickness(1),
            CornerRadius = new CornerRadius(10), Padding = new Thickness(8, 1, 8, 2), Margin = new Thickness(6, 0, 0, 0),
            Child = new TextBlock { Text = text, FontSize = 11.5, Foreground = (Brush)FindResource("Text2") },
        };

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
            bool ready = b != null && Store.Installed(b);
            StartText.Text = busy ? "Cancel download" : ready ? "Start" : b != null ? "Download and start" : "Start";
            StartIcon.Text = busy ? "" : ready || b == null ? "" : "";
            BtnStart.IsEnabled = b != null || busy;
            BtnBooks.IsEnabled = BtnFolder.IsEnabled = BtnFresh.IsEnabled = b != null && !busy;
            if (!busy)
            {
                if (b == null) SetStatus("", repo == null ? "No firmware to show." : $"No {device} build of this version. Devices it has: " +
                    string.Join(", ", builds.Where(x => (x.Repo ?? x.Name) == repo && x.Ref == gitRef).Select(x => x.Model)) + ".");
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
            try
            {
                foreach (var line in File.ReadAllLines(Path.Combine(Store.FramesDir, frame + ".keys")))
                {
                    var f = line.Split(' ');
                    if (f[0] == "size") { PreviewFrame.Width = double.Parse(f[1]); PreviewFrame.Height = double.Parse(f[2]); }
                    if (f[0] == "screen") { PreviewScreen.Margin = new Thickness(double.Parse(f[1]), double.Parse(f[2]), 0, 0); PreviewScreen.Width = double.Parse(f[3]); PreviewScreen.Height = double.Parse(f[4]); }
                }
            }
            catch (Exception) { PreviewScreen.Width = 0; }
        }

        static string Mb(long bytes) => bytes > 0 ? (bytes / 1048576.0).ToString("0.0") + " MB" : "size unknown";

        void SetStatus(string icon, string text) { StatusIcon.Text = icon; StatusText.Text = text; }

        void SaveSettings()
        {
            if (loading || App.RenderOnly) return;
            settings["device"] = device; settings["repo"] = repo; settings["ref"] = gitRef;
            settings["battery"] = (int)Battery.Value; settings["usb"] = Usb.IsChecked == true;
            Store.SaveSettings(settings);
        }

        // ---- actions ----------------------------------------------------------
        void Nav_Checked(object sender, RoutedEventArgs e)
        {
            if (SimPage == null) return;
            SimPage.Visibility = NavSim.IsChecked == true ? Visibility.Visible : Visibility.Collapsed;
            AboutPage.Visibility = NavAbout.IsChecked == true ? Visibility.Visible : Visibility.Collapsed;
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
                Store.Start(b, (int)Battery.Value, Usb.IsChecked == true);
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

        void AddBooks_Click(object sender, RoutedEventArgs e)
        {
            var b = Current; if (b == null) return;
            var dlg = new OpenFileDialog { Title = "Add books to the simulated SD card", Multiselect = true,
                Filter = "Books (*.epub;*.txt;*.xtc;*.xtch;*.md)|*.epub;*.txt;*.xtc;*.xtch;*.md|All files (*.*)|*.*" };
            if (dlg.ShowDialog(this) != true) return;
            var books = Path.Combine(Store.SdCard(b), "books");
            Directory.CreateDirectory(books);
            int n = 0;
            try
            {
                foreach (var f in dlg.FileNames) { File.Copy(f, Path.Combine(books, Path.GetFileName(f)), true); n++; }
                SetStatus("", $"Copied {Plural(n, "book")} to the SD card.");
            }
            catch (Exception ex) { SetStatus("", $"Copied {n}, then failed: " + ex.Message); }
        }
    }
}
