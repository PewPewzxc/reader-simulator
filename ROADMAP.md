# Possible future scope

Ideas that were discussed and could be built later. Nothing here is planned or promised yet.

## Add a firmware from a GitHub link
Anyone could ask for a firmware that is not in the list yet, from the web page or the Windows app.

**Why not instant:** a firmware release (`.bin`) is code for the reader's own chip; a PC or a browser cannot run it.
The simulator always builds a firmware from its source code, with a simulator library, which needs a full toolchain
(PlatformIO, a C++ compiler, Emscripten) and takes 5 to 20 minutes. So the build has to happen on GitHub, like the
builds of the firmwares already in the list.

**How it would work:**
1. An **Add a firmware** button on the web page and in the app. The person pastes a GitHub link (the repo or one of
   its release pages).
2. It opens a short, pre-filled GitHub issue form, so every request is public and needs a GitHub account (no spam).
3. **The owner approves it** with a label: a build runs that project's code on this repo's GitHub Actions, so the
   owner decides what gets built.
4. A workflow builds the requested repo's newest releases for the browser and for Windows, tests each one (as
   `pages.yml` and `build-firmwares.yml` do), and posts the result on the issue, for example "Built 2.40 for X4 Pro,
   X3" or "Failed: missing HalHaptics.h".
5. If it passes, the firmware is added to `sim-windows/firmwares.json` and shows up for everyone, in the web page and
   the app, typically 20 to 40 minutes after approval. From then on its new releases are built automatically.

**Limits:** only firmwares with public source on GitHub, built with PlatformIO and based on the CrossPoint, CrossInk
or FreeInk family (almost all current Xteink firmwares). Closed `.bin` firmwares (such as Xteink's factory firmware)
and firmwares in other languages (such as Rust) cannot run here. Some firmwares need small fixes before they build
in the simulator; their request fails with the reason until then.

**Work:** the issue form, the two buttons, a workflow that builds one requested repo and comments on the issue, and
adding a passing firmware to the list. About a day.

## Microsoft Store for the Windows app
Unsigned programs make Windows show "Windows protected your PC" (SmartScreen). Apps installed from the Microsoft
Store never show it: Microsoft signs the package, and updates are automatic. Registration is free for individual
developers (identity check with an ID).

**Work:** after the owner registers and reserves the app's name, `app.yml` would also build an MSIX package of the
app for the Store submission. Other compliant routes: Azure Artifact Signing (paid, individuals in the US and Canada
only) or SignPath Foundation (free for open-source projects, the certificate is in SignPath's name).
