"""Fixes for the simulator's downloaded libraries (.pio/libdeps/<env>).
Safe to run again: each fix is applied once. A fix whose text is not there
(another firmware, a newer simulator) is skipped; the build then shows if it
was still needed."""
import os
import re
import sys

L = sys.argv[1]


PENDING = None  # between group_begin() and group_end(): edits waiting to be applied together


def applicable(path, old, new):
    if not os.path.isfile(path):
        return False
    s = open(path, encoding="utf-8").read()
    return new in s or s.count(old) == 1


def group_begin():
    global PENDING
    PENDING = []


def group_end(label):
    """Apply the collected edits only if every one of them fits (half a feature does not compile)."""
    global PENDING
    edits, PENDING = PENDING, None
    missing = [e for e in edits if not applicable(*e)]
    if missing:
        print(f"patch_libdeps: {label} skipped, this simulator library differs ({missing[0][0]})")
        return False
    for e in edits:
        patch(*e)
    return True


def patch(path, old, new):
    if PENDING is not None:
        PENDING.append((path, old, new))
        return
    if not os.path.isfile(path):
        print(f"patch_libdeps: skipped, no {path}")
        return
    with open(path, encoding="utf-8") as f:
        s = f.read()
    if new in s:
        return
    if s.count(old) != 1:
        print(f"patch_libdeps: skipped, text not found in {path}: {old.splitlines()[0][:60]!r}")
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write(s.replace(old, new))


# gcc 15 compiles C as C23, where bool/true/false are keywords.
patch(L + "/QRCode/src/qrcode.h",
      "#ifndef __cplusplus\ntypedef unsigned char bool;",
      "#if !defined(__cplusplus) && (!defined(__STDC_VERSION__) || __STDC_VERSION__ < 202311L)\ntypedef unsigned char bool;")
# VARAGH additions to the device layer that the simulator's stand-ins lack.
patch(L + "/simulator/src/HalPowerManager.h",
      "  void begin();\n",
      "  void begin();\n  void setWifiIdleLowPowerAllowed(bool) {}\n")
patch(L + "/simulator/src/HalClock.h",
      "  void begin();\n",
      "  void begin();\n  void setDaylightSavingRuleSource(const uint8_t *) {}\n")
# CrossInk-Bookorbit asks whether the clock can be shown; no simulator version has it yet (the clock is the PC's).
C = L + "/simulator/src/HalClock.h"
if os.path.isfile(C) and "canDisplayTime" not in open(C, encoding="utf-8").read():
    patch(C, "  bool isAvailable() const { return _available; }\n",
          "  bool isAvailable() const { return _available; }\n  bool canDisplayTime() const { return _available; }\n")
# CrossNotes uses Arduino's String::toLowerCase, which the simulator's String stand-in lacks.
W = L + "/simulator/src/WString.h"
if os.path.isfile(W) and "toLowerCase" not in open(W, encoding="utf-8").read():
    patch(W, "  void trim() {\n",
          "  void toLowerCase() {  // ASCII only, like Arduino's tolower in the C locale\n"
          "    for (auto &c : s)\n      if (c >= 'A' && c <= 'Z')\n        c = static_cast<char>(c - 'A' + 'a');\n  }\n"
          "  void trim() {\n")
# Pictures of the battery icon: VARAGH_SIM_BATTERY=<0-100> sets the level and
# VARAGH_SIM_USB=0 unplugs the cable (defaults: 100 and plugged in).
patch(L + "/simulator/src/HalPowerManager.cpp",
      "uint16_t HalPowerManager::getBatteryPercentage() const { return 100; }",
      "uint16_t HalPowerManager::getBatteryPercentage() const {\n"
      "  const char *level = std::getenv(\"VARAGH_SIM_BATTERY\");\n"
      "  return level ? static_cast<uint16_t>(std::atoi(level)) : 100;\n}")
patch(L + "/simulator/src/HalGPIO.cpp",
      "bool HalGPIO::isUsbConnected() const { return true; }",
      "bool HalGPIO::isUsbConnected() const {\n"
      "  const char *usb = std::getenv(\"VARAGH_SIM_USB\");\n"
      "  return !(usb && usb[0] == '0');\n}")
patch(L + "/simulator/src/HalPowerManager.cpp",
      "#include \"HalPowerManager.h\"\n",
      "#include \"HalPowerManager.h\"\n\n#include <cstdlib>\n")
# Lion: the Control Center asks for one full refresh after closing (no-op on screen).
patch(L + "/simulator/src/HalDisplay.h",
      "  void begin(bool seamless);\n",
      "  void begin(bool seamless);\n  void fullRefreshNext() {}\n")
# Windows: MD5Builder takes the OpenSSL path; compat/openssl/md5.h provides MD5.
for name in ("MD5Builder.h", "MD5Builder_linux.h"):
    patch(L + "/simulator/src/" + name, "#elif defined(__linux__)\n", "#elif defined(__linux__) || defined(_WIN32)\n")
# Input scripts: DRAG:x1,y1,x2,y2[,ms] moves the finger every 40 ms, like a real
# slide. SWIPE only sends finger-down and finger-up, so sliders jump to the start.
G = L + "/simulator/src/HalGPIO.cpp"
patch(G, "  TouchUp,\n  HomeDown,", "  TouchUp,\n  TouchMove,\n  HomeDown,")
patch(G, '} else if ((key == "TAP" || key == "SWIPE") &&',
      '} else if ((key == "TAP" || key == "SWIPE" || key == "DRAG") &&')
patch(G, 'const bool swipe = key == "SWIPE";', 'const bool swipe = key != "TAP";')
patch(G, "              {atMs, SyntheticAction::TouchDown, -1, x1, y1});\n",
      "              {atMs, SyntheticAction::TouchDown, -1, x1, y1});\n"
      "          const int steps = key == \"DRAG\" ? std::max(1, static_cast<int>(duration / 40)) : 0;\n"
      "          for (int i = 1; i < steps; ++i)\n"
      "            syntheticEvents.push_back({atMs + duration * i / steps, SyntheticAction::TouchMove, -1,\n"
      "                                       x1 + (x2 - x1) * i / steps, y1 + (y2 - y1) * i / steps});\n")
patch(G, "    case SyntheticAction::TouchUp:\n      endTouch(event.logicalNx, event.logicalNy);\n      break;\n",
      "    case SyntheticAction::TouchUp:\n      endTouch(event.logicalNx, event.logicalNy);\n      break;\n"
      "    case SyntheticAction::TouchMove:\n      moveTouch(event.logicalNx, event.logicalNy);\n      break;\n")

# Device frame (CROSSPOINT_SIM_FRAME=<dir>/<model>): the reader drawn round the screen, keys clickable.
# The module lives in overlay/; copy it in, then hook it into drawing and mouse input.
group_begin()  # all of the frame or none of it (older simulator libraries differ)
D = L + "/simulator/src/HalDisplay.cpp"
# The older crosspoint-simulator library (YACP, inx, ...) draws the whole panel and has other include lines;
# the newer crossink-simulator one hides a 2 px bezel edge (SIMULATOR_BEZEL_INSET). With the frame both
# show the same visible part, so the frame's screen hole (panel minus 2 px each side) fits both.
OLD_LIB = os.path.isfile(D) and "SIMULATOR_BEZEL_INSET" not in open(D, encoding="utf-8").read()
if OLD_LIB:
    patch(D, '#include "HalDisplay.h"\n', '#include "HalDisplay.h"\n#include "SimulatorDeviceFrame.h"\n')
else:
    patch(D, '#include "SimulatorInput.h"\n', '#include "SimulatorDeviceFrame.h"\n#include "SimulatorInput.h"\n')
# older versions of the older library read pendingPresent with load(), newer ones with exchange(false)
PRESENT = "exchange(false)" if OLD_LIB and "pendingPresent.exchange(false) && !screenshotDue" in open(D, encoding="utf-8").read() else "load()"
patch(D, f"  if (!pendingPresent.{PRESENT} && !screenshotDue)\n    return;\n",
      f"  if (!pendingPresent.{PRESENT} && !screenshotDue && !simFrameTakeRedraw())\n    return;\n")
patch(D, "  const bool isPortrait = isPortraitOrientation(orientation);\n  *width =",
      "  const bool isPortrait = isPortraitOrientation(orientation);\n"
      "  if (simFrameActive()) {\n    simFrameWindowSize(isPortrait, width, height);\n    return;\n  }\n  *width =")
patch(D, "  switch (orientation) {\n  case GfxRenderer::Portrait: {\n    // dst centre",
      "  if (simFrameActive()) {\n"
      + ("    const SDL_Rect src = {2, 2, DISPLAY_WIDTH - 4, DISPLAY_HEIGHT - 4};  // what the newer library shows\n"
         if OLD_LIB else "") +
      "    // how far the reader is turned: Portrait upright, LandscapeClockwise = turned right\n"
      "    const int angle = orientation == GfxRenderer::Portrait             ? 0\n"
      "                      : orientation == GfxRenderer::LandscapeClockwise ? 90\n"
      "                      : orientation == GfxRenderer::PortraitInverted   ? 180\n"
      "                                                                       : 270;\n"
      "    simFrameRender(sdl_renderer, texture, src, angle, currentWindowWidth, currentWindowHeight);\n"
      "  } else\n"
      "  switch (orientation) {\n  case GfxRenderer::Portrait: {\n    // dst centre")
G_INC = '#include "SimulatorLifecycle.h"\n' if OLD_LIB else '#include "SimulatorInput.h"\n'
patch(G, G_INC, '#include "SimulatorDeviceFrame.h"\n' + G_INC)
patch(G, "  HomeDown,\n  HomeUp,\n", "  HomeDown,\n  HomeUp,\n  MouseDown,\n  MouseUp,\n")
if OLD_LIB:  # it only has touch in turned-screen coordinates; the frame gives panel ones (as the newer library)
    def at_panel(src, name):
        """The library's own beginTouch/moveTouch/endTouch, taking panel coordinates (its fields differ by version)."""
        m = re.search(r"^void %s\(float logicalNx, float logicalNy\) \{\n.*?^\}\n" % name, src, re.M | re.S)
        if not m:
            return None
        body = m.group(0).replace(f"void {name}(float logicalNx, float logicalNy)",
                                  f"void {name}AtPanel(float panelNx, float panelNy)")
        body = re.sub(r"^  float panelN[xy] = 0\.0f;\n|^  logicalToPanelNormalized\(logicalNx, logicalNy, panelNx, panelNy\);\n",
                      "", body, flags=re.M).replace("moveTouch(logicalNx, logicalNy)", "moveTouchAtPanel(panelNx, panelNy)")
        return None if "logical" in body else body
    g_src = open(G, encoding="utf-8").read() if os.path.isfile(G) else ""
    helpers = [at_panel(g_src, n) for n in ("beginTouch", "moveTouch", "endTouch")]
    if all(helpers):
        patch(G, "void beginHomeKey() {\n", "".join(helpers) + "\nvoid beginHomeKey() {\n")
    else:
        patch(G, "(touch functions of this library not recognised)", "")  # makes the whole frame group skip
patch(G, "void processSyntheticEvents() {\n", r'''// Mouse on the device frame: the keys press like the real ones, the screen is
// the touchscreen. kind: 0 down, 1 up, 2 move (window coordinates).
std::string frameMouseKey;
void frameMouse(int kind, int x, int y) {
  float nx = 0.0f, ny = 0.0f;
  const std::string hit = simFrameHit(x, y, &nx, &ny);
  if (kind == 0) {
    if (hit == "SCREEN") {
      beginTouchAtPanel(nx, ny);
      return;
    }
    if (hit.empty())
      return;
    frameMouseKey = hit;
    simFrameSetPressed(hit);
    if (hit == "HOME") {
      beginHomeKey();
      return;
    }
    const int b = namedButton(hit);
    if (b >= 0) {
      pressedThisFrame[b] = true;
      syntheticButtonDown[b] = true;
      buttonPressTime[b] = SDL_GetTicks();
    }
  } else if (kind == 2) {
    if (touchState.down && hit == "SCREEN")
      moveTouchAtPanel(nx, ny);
  } else {
    if (touchState.down)
      endTouchAtPanel(hit == "SCREEN" ? nx : touchState.currentNx, hit == "SCREEN" ? ny : touchState.currentNy);
    if (frameMouseKey.empty())
      return;
    if (frameMouseKey == "HOME") {
      endHomeKey();
    } else if (const int b = namedButton(frameMouseKey); b >= 0) {
      releasedThisFrame[b] = true;
      syntheticButtonDown[b] = false;
    }
    frameMouseKey.clear();
    simFrameSetPressed("");
  }
}

void processSyntheticEvents() {
''')
patch(G, "    case SyntheticAction::HomeUp:\n      endHomeKey();\n      break;\n",
      "    case SyntheticAction::HomeUp:\n      endHomeKey();\n      break;\n"
      "    case SyntheticAction::MouseDown:\n      frameMouse(0, static_cast<int>(event.logicalNx), static_cast<int>(event.logicalNy));\n      break;\n"
      "    case SyntheticAction::MouseUp:\n      frameMouse(1, static_cast<int>(event.logicalNx), static_cast<int>(event.logicalNy));\n      break;\n")
# Firmwares with their own simulator home-key reader (VARAGH's src/simulator/SimulatorHomeKeyInput) poll
# the keyboard H key directly, so scripted HOME and frame clicks never reached them. Hold H in SDL's key
# state while the home key is down. shortcut: writes SDL's internal state; a real H key event resets it.
patch(G, "  homeKeyDown = true;\n  homeKeyPressedThisFrame = true;\n",
      "  homeKeyDown = true;\n  homeKeyPressedThisFrame = true;\n"
      "  const_cast<Uint8 *>(SDL_GetKeyboardState(nullptr))[HOME_KEY_SCANCODE] = 1;\n")
patch(G, "    homeKeyTappedThisFrame = true;\n  }\n  homeKeyDown = false;\n",
      "    homeKeyTappedThisFrame = true;\n  }\n  homeKeyDown = false;\n"
      "  const_cast<Uint8 *>(SDL_GetKeyboardState(nullptr))[HOME_KEY_SCANCODE] = 0;\n")
# Scripts: MOUSE:x,y[,holdMs] clicks the window at x,y (frame pixels), like a real mouse.
patch(G, '      } else if ((key == "TAP" || key == "SWIPE" || key == "DRAG") &&',
      '      } else if (key == "MOUSE" && secondColon != std::string::npos) {\n'
      '        int mx = 0, my = 0;\n        unsigned long hold = 120;\n'
      '        if (std::sscanf(item.substr(secondColon + 1).c_str(), "%d,%d,%lu", &mx, &my, &hold) >= 2) {\n'
      '          syntheticEvents.push_back({atMs, SyntheticAction::MouseDown, -1, float(mx), float(my)});\n'
      '          syntheticEvents.push_back({atMs + hold, SyntheticAction::MouseUp, -1, float(mx), float(my)});\n'
      '        }\n'
      '      } else if ((key == "TAP" || key == "SWIPE" || key == "DRAG") &&')
# Real mouse events go to the frame when one is shown.
patch(G, "  while (SDL_PollEvent(&e) != 0) {\n    if (e.type == SDL_QUIT) {\n      quitRequested.store(true);\n    } else if (e.type == SDL_KEYDOWN && !e.key.repeat) {",
      "  while (SDL_PollEvent(&e) != 0) {\n"
      "    if (simFrameActive() && (e.type == SDL_MOUSEBUTTONDOWN || e.type == SDL_MOUSEBUTTONUP || e.type == SDL_MOUSEMOTION)) {\n"
      "      if (e.type == SDL_MOUSEMOTION)\n        frameMouse(2, e.motion.x, e.motion.y);\n"
      "      else if (e.button.button == SDL_BUTTON_LEFT)\n"
      "        frameMouse(e.type == SDL_MOUSEBUTTONDOWN ? 0 : 1, e.button.x, e.button.y);\n"
      "      continue;\n    }\n"
      "    if (e.type == SDL_QUIT) {\n      quitRequested.store(true);\n    } else if (e.type == SDL_KEYDOWN && !e.key.repeat) {")
if group_end("device frame"):
    OVERLAY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "overlay")
    for name in ("SimulatorDeviceFrame.h", "SimulatorDeviceFrame.cpp"):
        src, dst = os.path.join(OVERLAY, name), L + "/simulator/src/" + name
        data = open(src, "rb").read()
        if not os.path.isfile(dst) or open(dst, "rb").read() != data:
            open(dst, "wb").write(data)
