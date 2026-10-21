# Credits: web simulator

Unofficial. Not made by, affiliated with or endorsed by Xteink. The simulator is an approximation of a real reader.

## Firmwares (each build includes its licence as `builds/<id>/LICENSE-firmware.txt`)
Every firmware is built from its public source at the release tag (or branch) listed in the page's `builds.json`, unchanged.
All of them are MIT licensed, based on CrossPoint Reader (c) 2025 Dave Allie, with their own authors:
PewPewzxc/VARAGH, crosspoint-reader/crosspoint-reader, uxjulia/crossink, Sichroteph/YACP, HilbergK/CrossNotes, dito94/CrossDiTo,
ashokslsk/PocketDeck-OS, padge01/xteink-pokemon-game, lauren-alexandra/duet-xteink, Mumfee/CrossSmudge, 0xKnowles/CrossPlant, 0x1abin/crossmux.

## Inside every build
- Simulator library: uxjulia/crossink-simulator and uxjulia/crosspoint-simulator (MIT), with small patches
  for Windows and the browser (sim-windows/patch_libdeps.py and web/patch_work.py).
- SDL2 (zlib licence), as the Emscripten port.
- Emscripten runtime (MIT), musl libc (MIT), LLVM libc++ / libc++abi (Apache 2.0 with LLVM exception).
- Libraries the firmwares use: ArduinoJson (MIT), PNGdec and JPEGDEC (Apache 2.0), QRCode (MIT),
  expat (MIT), miniz (MIT), uzlib (zlib), FreeType parts in freeink-sdk (FreeType licence), as listed in each
  firmware's own notices.

## Sample SD card
- Pride and Prejudice and The Adventures of Sherlock Holmes from Standard Ebooks (CC0 1.0, public domain).
- English dictionary built from WordNet 3.0, (c) Princeton University, WordNet License (`dictionaries/wordnet/LICENSE.txt`).

## This site
Page, service worker (`coi-sw.js`) and device frames: Reader Simulator, MIT, (c) 2026 VARAGH contributors.
