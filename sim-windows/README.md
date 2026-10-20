# Reader simulator on Windows

Builds and runs the X4 Pro (and X3 / X4 Classic) desktop simulator of any
CrossInk-based firmware **source folder** (VARAGH, CrossInk, ...) on Windows,
windowless, so screens can be scripted and screenshotted.
A finished `.bin` cannot run here: it is machine code for the reader's chip.

Nothing in the firmware is edited. All Windows fixes live in this folder;
the simulator libraries PlatformIO downloads get small patches from
`patch_libdeps.py` (inside `<firmware>/.pio/libdeps/`, build output only).

## Needs
- Git Bash, PlatformIO (`~/.platformio/penv`), WinLibs g++ on PATH, ffmpeg (for PNGs)
- SDL2 MinGW dev package in `deps/` (official release
  `SDL2-devel-2.32.10-mingw.tar.gz` from github.com/libsdl-org/SDL, unpacked there)

## Use
```bash
./build.sh ../../github/varagh-lion-1.3.0          # any firmware folder; env defaults to x4-pro-simulator
./build.sh ../../github/crossink-762 x4-classic-simulator
./sim.sh '2000:TAP:120,651;5000:QUIT' '4000:settings'   # runs the firmware built last
./check-lion-screens.sh                            # Control Center + Dictionaries pictures
```
Script steps: `TAP:x,y[,ms]`, `SWIPE:x1,y1,x2,y2[,ms]` (finger down + up only),
`DRAG:x1,y1,x2,y2[,ms]` (moves every 40 ms, for sliders), `BACK ENTER LEFT RIGHT UP DOWN HOME POWER SLEEP QUIT`.
Each firmware gets its own SD card: `cards/<folder>/fs_/` (books in `fs_/books/`).
Pictures: `cards/<folder>/shots/` or `SIM_SHOTS=<dir>`.
Sleep/wake: waking (POWER after SLEEP) restarts `program.exe`. The new run drops the script and pictures on purpose
(no endless sleep loop) and uses `CROSSPOINT_SIM_INPUT_SCRIPT_AFTER_WAKE` / `CROSSPOINT_SIM_SCREENSHOTS_AFTER_WAKE`
instead, e.g. `...;3000:POWER` + `AFTER_WAKE='2500:QUIT'`. On Windows the restart is a new process (MinGW `execvp`
starts a new process and the old one exits), so wait for every `program.exe` from that folder, not only the one you started.

## Many firmwares at once (release builds)
```bash
python -I tools/latest_refs.py | bash tools/try_all.sh 3   # newest version of every catalogue entry, every model
bash tools/summary.sh                                      # last result per firmware x model, first error
bash tools/make_release.sh                                 # zips + index.json + index.local.json in dev/rsim/release-staging
```
`try_firmware.sh` keeps each passing build in `<firmware>/.rsim-out/<env>/` (PlatformIO empties
`.pio/build` when the project config changes), and `make_release.sh` packs from there.

## What each fix is
| Fix | Why |
| --- | --- |
| `bin/sdl2-config.cmd` (written by build.sh) | platformio.ini runs `sdl2-config` through cmd.exe; adds `-DSDL_MAIN_HANDLED`, `-lws2_32` |
| `compat/win_sim_prelude.h` (force-included) | MinGW lacks `posix_memalign`, `std::aligned_alloc`, `strlcpy`, `setenv/unsetenv`, `fsync`, 2-arg `mkdir`, `lstat`, `realpath`, `localtime_r`, `uint`; expat's `winconfig.h` includes `<memory.h>`, which on a case-insensitive disk is the firmware's `lib/Memory/Memory.h` |
| `compat/win_sockets.h` + `sys/socket.h` etc. | simulator web server / HTTP client written for POSIX sockets; mapped to Winsock (compiles and links; file transfer over Wi-Fi not tested) |
| `compat/sys/statvfs.h`, `sys/wait.h`, `dlfcn.h` | SD-card size via `std::filesystem::space`; curl exit status; stack-check build only |
| `compat/openssl/md5.h` | the only OpenSSL use (KOReader document ids); self-check `tests/md5_check.cpp` |
| `compat/esp_random.h`, `-DtskNO_AFFINITY`, `-DportNUM_PROCESSORS` | games use them; the simulator library lacks them (Linux needs these too) |
| `patch_libdeps.py` | QRCode C23 `bool`; VARAGH no-ops `setWifiIdleLowPowerAllowed`, `setDaylightSavingRuleSource`, `fullRefreshNext`; `VARAGH_SIM_BATTERY` / `VARAGH_SIM_USB`; MD5Builder on Windows; new `DRAG` script step. A fix whose text is missing is skipped |
| `adapter.py` (build.sh, launcher download, try_firmware.sh) | CrossPoint-family downloads without a simulator setup get one in `platformio.local.ini` (crosspoint-simulator's sample envs at the library commit from the firmware's date; `--newest` / `platformio.local.ini.dated` after a failed build); `-DRSIM_CROSSPOINT_COMPAT` turns on `settimeofday`/`strcasestr` in `compat/win_sim_prelude.h`, `compat/openssl/sha.h` gives SHA1/SHA256 (checks: `tests/sha_check.cpp`, `tests/crosspoint_prelude_check.cpp`). CrossPoint 1.6.5 and 2.0.0rc build for all three models |
| `win_sim_prelude.h`: `fopen(const wchar_t*)` | CrossInk 1.6.1's smoke test passes `std::filesystem::path::c_str()` (wchar_t on Windows) to `fopen`; self-check `tests/wfopen_check.cpp` |
| `patch_libdeps.py`: `HalClock::canDisplayTime`, `String::toLowerCase` | stand-ins the simulator libraries lack (CrossInk-Bookorbit, CrossNotes) |
| frame on the older `crosspoint-simulator` library | `patch_libdeps.py` picks its anchors (`OLD_LIB`) and crops the same 2 px edge the newer library hides, so one set of frames fits both |
| `pin_simlib.py`: short pins, `GITHUB_TOKEN`, `.rsim-pin.json` | a library pinned by a short commit id cannot be fetched by PlatformIO, so it is written out in full; answers are cached per checkout |
| `build.sh` install lock | PlatformIO's package cache breaks when two installs run at once (WinError 32) |
| `win_sim_prelude.h`: `_set_fmode(_O_BINARY)` | the SD-card stand-in opens files without `O_BINARY`; in Windows' text mode CR LF became LF and reading stopped at byte 0x1A, so no EPUB opened ("Failed to index") and caches were damaged; self-check `tests/binmode_check.cpp` |
| `build.sh`: `-ffile-prefix-map`, `-fmacro-prefix-map`, `-g0`, `strip` | builds get published: no user name or folder of this PC inside `program.exe`; `make_release.sh` refuses a build that still contains the Windows user name or the e-mail name (plus `RSIM_PRIVATE_WORDS`) |
| `compat/utf8.manifest` + `compat/set_manifest.py` (run by build.sh after `strip`) | UTF-8 code page for program.exe (Windows 10 1903+): card and frame folders with non-ASCII letters (user names) work; replaces MinGW's default manifest (same id and language) |
| `-Wno-narrowing`, `PYTHONUTF8=1` | g++ narrowing errors; PlatformIO prints Persian text to the console |

After changing anything in `compat/`, delete `<firmware>/.pio/build/<env>`:
SCons does not notice changes to a force-included header.
