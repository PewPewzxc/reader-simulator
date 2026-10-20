# Credits

This project only puts other people's work together for Windows. Thank you to all of them.

## Simulator libraries
The firmwares are built against one of these desktop simulator libraries (they replace the reader's hardware):

| Library | Author | Licence |
| --- | --- | --- |
| [uxjulia/crossink-simulator](https://github.com/uxjulia/crossink-simulator) | Julia Nguyen (uxjulia) | MIT |
| [crosspoint-reader/crosspoint-simulator](https://github.com/crosspoint-reader/crosspoint-simulator) (formerly uxjulia/crosspoint-simulator) | crosspoint-reader contributors, uxjulia | MIT (declared in its `library.json`) |

Our Windows changes to them are made at build time by `sim-windows/patch_libdeps.py` and `sim-windows/overlay/`.

## Other parts in every download
| Part | Licence |
| --- | --- |
| [SDL2](https://github.com/libsdl-org/SDL) 2.32.10 (`SDL2.dll`) | zlib |
| GCC runtime (`libgcc_s_seh-1.dll`, `libstdc++-6.dll`) from [WinLibs](https://winlibs.com) | GPL 3 with the GCC Runtime Library Exception |
| `libwinpthread-1.dll` (MinGW-w64) | MIT and BSD style |

## Firmwares
Each download contains the firmware's own licence as `LICENSE-firmware.txt` and its `build.json` names
the exact source (repo, version, commit). All firmwares below are forks of
[CrossPoint Reader](https://github.com/crosspoint-reader/crosspoint-reader) (MIT, Copyright (c) 2025 Dave Allie)
and keep its MIT licence.

| Firmware | Authors | Licence |
| --- | --- | --- |
| [PocketDeck OS](https://github.com/ashokslsk/PocketDeck-OS) | ashokslsk and contributors (licence: Copyright (c) 2025 Dave Allie) | MIT |
| [CrossDiTo](https://github.com/dito94/CrossDiTo) | dito94 and contributors (licence: Copyright (c) 2025 Dave Allie) | MIT |
| [CrossNotes](https://github.com/HilbergK/CrossNotes) | HilbergK and contributors (licence: Copyright (c) 2025 Dave Allie) | MIT |
| [duet](https://github.com/lauren-alexandra/duet-xteink) | lauren-alexandra and contributors (licence: Copyright (c) 2025 Dave Allie; 2026 Lauren Landau, for Duet modifications and original additions) | MIT |
| [Xteink Pokemon game](https://github.com/padge01/xteink-pokemon-game) | padge01 and contributors (licence: Copyright (c) 2025 Dave Allie) | MIT |
| [VARAGH](https://github.com/PewPewzxc/VARAGH) | PewPewzxc and contributors (licence: Copyright (c) 2025 Dave Allie; 2026 PewPewzxc (VARAGH changes)) | MIT |
| [YACP](https://github.com/Sichroteph/YACP) | Sichroteph and contributors (licence: Copyright (c) 2025 Dave Allie) | MIT |
| [CrossInk](https://github.com/uxjulia/crossink) | uxjulia and contributors (licence: Copyright (c) 2025 Dave Allie) | MIT |

## Device drawings
`device-frames/` are our own drawings of the Xteink X3, X4 Classic and X4 Pro (MIT, this repo), made from the
official sizes. Xteink is named only to say which reader is simulated; this project is not made by Xteink.
