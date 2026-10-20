# Plan: ready-made Windows downloads of the reader simulator

Nothing here is published yet. Publishing needs your yes.

## What a user gets
1. **One download, `ReaderSimulator-Windows.zip`** (about 15 MB) from the tool's GitHub Releases page:
   - `Reader Simulator.exe`: the launcher, packed with PyInstaller so no Python is needed;
   - the three device frames and their key maps;
   - the simulator's licences and credits.
2. **The launcher's firmware menu** lists ready-made builds, one per firmware version × model, about 7 MB each.
   - Picking one downloads that zip, checks its SHA‑256 and unpacks it into the user's folder.
   - Start then works straight away. No compiler, no PlatformIO, no Git.
3. **Advanced use (optional):** "Build it yourself" stays for any other GitHub link or local folder.
   - It needs the developer tools (Git, PlatformIO, WinLibs g++), and the launcher would show how to install them.

## Where the builds are made
- **What builds them:** GitHub Actions in the tool's own repo, on `windows-latest`. It's free for public repos.
- **Workflow `build-firmwares.yml`:**
  1. **When it runs:** a weekly schedule, plus a manual "Run workflow" button.
  2. **What's new:** it reads `firmwares.json` and asks GitHub for each firmware's newest release.
  3. **What it builds:** every (firmware, version, model) not built yet becomes one job in a matrix.
     Each job runs `tools/try_firmware.sh <repo> <tag> <env>`, the same script I test with here.
     That script downloads, pins the simulator library, builds, and saves a picture.
  4. **What it keeps:** jobs whose build and smoke test pass upload `program.exe` + DLLs + the firmware's LICENSE as a zip.
  5. **What it publishes:** the zips go to a release named `builds-YYYY-MM-DD`, with an `index.json` listing firmware, version, model, size, sha256 and URL.
- **Toolchain on the runner:** the same pieces as here, with pinned versions:
  - WinLibs g++ 16 (`winget`, or the MSYS2 UCRT64 gcc already installed on the runner);
  - SDL2 2.32.10 from libsdl-org;
  - PlatformIO from pip.
- **Failures:** a firmware that fails to build just isn't offered. The failure log is attached to the run, so the firmware's author could be told.

## Licences (checked)
- **Firmwares in the menu:** all MIT (VARAGH, CrossInk, CrumBLE, YACP, CrossPoint and the rest checked so far). Builds may be shared if each zip carries the firmware's LICENSE and names its authors.
- **Other parts:**

  | Part | Licence |
  |---|---|
  | Simulator libraries (uxjulia/crossink-simulator, crosspoint-reader/crosspoint-simulator) | MIT |
  | SDL2 | zlib |
  | GCC runtime DLLs | GPL with the runtime exception |
  | Device frames | our own drawings, MIT |

- **Xteink's photos:** stay out of the repo.
- **Xteink factory firmware:** never redistributed, and it can't run (closed .bin; X4 Classic / Pro files are encrypted).
- **Xteink's name:** used only to say which reader is simulated, and the repo name avoids it.

## Safety
- Builds come only from the catalogue repos, at release tags. Each zip has a SHA‑256 in `index.json`, and the launcher refuses a mismatch.
- The exe files won't be signed (a certificate costs money yearly). Windows SmartScreen will warn on first start ("More info → Run anyway"); the README says so.

## Status of the firmware menu (tested on this PC)
See `firmwares.json` and the survey in `tools/survey.tsv`. readme.club lists 53 Xteink firmwares:
- **20 have a simulator setup.** The frame, with clickable keys, works for the ones on the newer `crossink-simulator` library (VARAGH, CrossInk and 7 more). The ones on the older `crosspoint-simulator` library (YACP, CrumBLE, ...) run in a plain window for now.
- **30 have no simulator setup** (CrossPoint Reader itself, InkPointX, Papyrix, ...). They need an "adapter" that adds one; not built yet.
- **3 aren't PlatformIO projects** (for example TernOS in Rust), so they can't be supported.

## Still to do before a first release
1. Frames for the older simulator library, so YACP / CrumBLE also show the reader around the screen.
2. The adapter for firmwares without a simulator setup, starting with CrossPoint Reader.
3. Test turning the reader to landscape inside the frame.
4. Pack the launcher as an .exe and switch its menu to the ready-made builds (`index.json`).
5. Write the GitHub Actions workflow and do a first run in a private test repo.
6. README with pictures, credits, and the SmartScreen note.

## Questions for you
- Repo name and owner: for example `PewPewzxc/reader-simulator`? Public from the start, or private until tested?
- First release: only firmwares that pass the build + picture test, or also list "builds on your PC" ones?
