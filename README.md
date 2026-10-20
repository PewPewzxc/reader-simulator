# Reader Simulator

Try e-reader firmwares for the Xteink X3, X4 Classic and X4 Pro without the reader.

## ▶ [Open the simulator in your browser](https://pewpewzxc.github.io/reader-simulator/)

**https://pewpewzxc.github.io/reader-simulator/**: nothing to install, free, works in Chrome, Edge, Firefox and
Safari on a computer, tablet or phone.

1. Pick a device (X4 Pro, X4 Classic or X3), a firmware and a version.
2. Press **Start**. The firmware loads once (about 10 MB) and your browser keeps it.
3. Use the reader like the real one: click or tap its keys, and on the X4 Pro touch its screen.
   The **Controls** card under the reader lists every key and gesture.

Every new simulated SD card comes with two free books and an English dictionary, so you can start reading and
looking up words straight away. **Add books** puts your own EPUB and TXT files on it; they stay in your browser and
are never uploaded. Each firmware offers its newest versions (3 by default), and new releases appear by themselves.

This is an unofficial community tool, not made by or affiliated with Xteink.

| X4 Pro | X4 Classic | X3 |
| --- | --- | --- |
| ![X4 Pro](docs/live-x4-pro-touch-down-key.png) | ![X4 Classic](docs/live-x4-classic-down-ok-back.png) | ![X3](docs/live-x3-down-ok-back.png) |

The reader turns when the firmware turns the page sideways:

![X4 Pro turned](docs/live-x4-pro-turned-right.png)

## Windows app (optional)
The same simulator as a Windows program, for working offline or with books from a folder on your PC.
Most people do not need it: the browser version above does the same.

1. Download [`ReaderSimulator-Setup.exe`](https://github.com/PewPewzxc/reader-simulator/releases/latest/download/ReaderSimulator-Setup.exe)
   (also on the [Releases](../../releases) page) and run it. No administrator rights are needed.
2. The program is not signed yet, so Windows may say "Windows protected your PC". Click **More info**, then
   **Run anyway**.
3. Open **Reader Simulator**, pick a device and a firmware, and click **Start**. The firmware downloads the first
   time (about 7 MB). The **Controls** page lists every key and gesture.
4. **Add books** puts your own books on the simulated SD card; **Fresh SD card** empties it.

## Which firmwares
The list comes from [`sim-windows/firmwares.json`](sim-windows/firmwares.json). A firmware is offered when its own source code
builds and starts in the simulator. The builds are made by GitHub Actions in this repo
([`build-firmwares.yml`](.github/workflows/build-firmwares.yml)) straight from each firmware's
GitHub release, and every download is checked against its SHA-256 before it runs.

Firmwares on the older simulator library (YACP and other CrossPoint forks) show the same reader drawing.

The factory firmware from Xteink cannot run here: it is closed source, and this simulator builds firmwares from source.

## The device drawings
`device-frames/frames/` has our own drawings of the three readers (SVG + PNG) and the key areas (`.keys`).
They were drawn from the official sizes, not copied from photos.

| X4 Pro | X4 Classic | X3 |
| --- | --- | --- |
| ![](docs/x4-pro-v3.png) | ![](docs/x4-classic-v3.png) | ![](docs/x3-v3.png) |

## Build a firmware yourself
You need Git for Windows, Python 3.12, PlatformIO (`pip install platformio`), the WinLibs (or MSYS2 UCRT64) g++,
ffmpeg, and the SDL2 MinGW package `SDL2-devel-2.32.10-mingw.tar.gz` unpacked into `sim-windows/deps/`.
```bash
cd sim-windows
python -I tools/latest_refs.py | bash tools/try_all.sh      # build + test every firmware in the list
bash tools/make_release.sh                                   # zips + index.json
```
`sim-windows/README.md` lists every Windows fix. The firmwares' own code is never changed.

## Licence
MIT, see [LICENSE](LICENSE). Firmwares, simulator libraries and SDL2 keep their own licences: see [CREDITS.md](CREDITS.md).
Xteink, X3, X4 and X4 Pro are named only to say which reader is simulated. This project is not made by Xteink.

## Building it yourself
| Folder | What | How |
| --- | --- | --- |
| `sim-windows/` | builds a firmware's simulator on Windows (Git Bash, PlatformIO, WinLibs g++, SDL2) | see `sim-windows/README.md` |
| `app/` | the Windows app (WPF, .NET Framework 4.8: runs on any Windows 10/11) | `app/build.ps1` (per-user .NET SDK in `tools/dotnet`) |
| `installer/` | the setup program (Inno Setup 6, per-user, no admin) | compile `installer/ReaderSimulator.iss`; `installer/test-clean.ps1` tests install, app self-test and uninstall |
| `web/` | the browser version (Emscripten / WebAssembly) | `web/build.py`; serve `web/build/out/` with `web/serve.py` |
| `device-frames/` | the reader drawings and key areas | `device-frames/tools/gen.py` |

The app downloads builds only over HTTPS from this repo's releases and checks each one's SHA-256 before it
unpacks or runs anything. It sends nothing anywhere.
