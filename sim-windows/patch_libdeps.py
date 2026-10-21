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
    # The sleep loop (startDeepSleep) only listened to the keyboard: with the frame the reader could not be
    # woken by clicking its keys, and its window was never repainted. Same loop in both libraries.
    patch(G, '      if (e.type == SDL_KEYDOWN && !e.key.repeat &&\n          scancodeToButton(e.key.keysym.scancode) >= 0) {\n        clearButtonState();\n        SimulatorLifecycle::rebootAsPowerWake();\n      }\n',
          '      if (e.type == SDL_KEYDOWN && !e.key.repeat &&\n          scancodeToButton(e.key.keysym.scancode) >= 0) {\n        clearButtonState();\n        SimulatorLifecycle::rebootAsPowerWake();\n      }\n      // Device frame while asleep: a click on a drawn key wakes the reader like the real key, and the\n      // window is drawn again when Windows asks (otherwise the sleep screen looks frozen).\n      if (simFrameActive() && e.type == SDL_MOUSEBUTTONDOWN && e.button.button == SDL_BUTTON_LEFT) {\n        float nx = 0.0f, ny = 0.0f;\n        const std::string key = simFrameHit(e.button.x, e.button.y, &nx, &ny);\n        if (!key.empty() && key != "SCREEN") {\n          clearButtonState();\n          SimulatorLifecycle::rebootAsPowerWake();\n        }\n      }\n      if (simFrameActive() && e.type == SDL_WINDOWEVENT) {\n        extern HalDisplay display;\n        simFrameRequestRedraw();\n        display.presentIfNeeded();\n      }\n')


# ---- API compatibility -----------------------------------------------------------------------------------
# Firmwares are written against one simulator library version; many pin an older one that lacks functions the
# newer crossink-simulator has (CrossNotes 1.1.1.1, CrossPlant, ...). These add the missing ones, with the newer
# library's names and arguments, to the library a firmware downloaded. The firmware's own code is never changed.
# Each is added only when the library does not have it yet, so a library that has it keeps its own.
def add_member(path, anchor, have, code, before=False):
    """Put `code` after (or before) the unique `anchor` line(s), unless the file already matches the regex `have`."""
    if not os.path.isfile(path):
        return
    s = open(path, encoding="utf-8").read()
    if re.search(have, s):
        return
    if s.count(anchor) != 1:
        print(f"patch_libdeps: compat skipped, anchor not found in {path}: {anchor.splitlines()[0][:60]!r}")
        return
    s = s.replace(anchor, code + anchor if before else anchor + code)
    open(path, "w", encoding="utf-8").write(s)


def add_to_class(path, class_head, have, code):
    """Put `code` right after the first 'public:' of the class that `class_head` opens."""
    if not os.path.isfile(path):
        return
    s = open(path, encoding="utf-8").read()
    if re.search(have, s) or s.count(class_head) != 1:
        return
    at = s.find("public:\n", s.index(class_head))
    if at < 0:
        return
    at += len("public:\n")
    open(path, "w", encoding="utf-8").write(s[:at] + code + s[at:])


SRC = L + "/simulator/src/"
# USB serial: buffer sizes (file transfer over USB) and a block read (CrossNotes, CrossPlant).
add_to_class(SRC + "HardwareSerial.h", "class HWCDC : public Stream {", r"setRxBufferSize\s*\(",
             "  size_t setRxBufferSize(size_t) { return 0; }  // reader simulator: no USB serial here\n"
             "  size_t setTxBufferSize(size_t) { return 0; }\n")
add_to_class(SRC + "HardwareSerial.h", "class HWCDC : public Stream {", r"read\s*\(\s*(const\s+)?uint8_t\s*\*",
             "  size_t read(uint8_t *buffer, size_t size) { (void)buffer; (void)size; return 0; }\n")
# Wi-Fi: disconnect with a timeout, which reports whether it finished (crossink-simulator's form).
add_member(SRC + "WiFi.h", "  void disconnect(bool wifioff = false, bool eraseap = false) {\n",
           r"disconnect\s*\([^)]*,[^)]*,[^)]*\)",
           "  bool disconnect(bool wifioff, bool eraseap, unsigned long timeoutMs) {\n"
           "    (void)timeoutMs;\n    disconnect(wifioff, eraseap);\n    return true;\n  }\n", before=True)
# Power button: the wake check with the firmware's settings (crossink-simulator's form).
add_member(SRC + "HalGPIO.h", "  bool verifyPowerButtonWakeup();\n", r"verifyPowerButtonWakeup\s*\(\s*uint16_t",
           "  bool verifyPowerButtonWakeup(uint16_t requiredDurationMs, bool shortPressAllowed) {\n"
           "    (void)requiredDurationMs;\n    (void)shortPressAllowed;\n    return verifyPowerButtonWakeup();\n  }\n")
# SD card file dates from the reader's clock offset: the simulator uses the PC's clock as it is.
add_to_class(SRC + "HalStorage.h", "class HalStorage {", r"installDateTimeCallback\s*\(",
             "  void installDateTimeCallback(const uint8_t *utcOffsetQuarterHoursBiased) { (void)utcOffsetQuarterHoursBiased; }\n")
# FreeRTOS: deleting a semaphore (a no-op: this library's static semaphores must not be freed).
if os.path.isfile(SRC + "freertos/semphr.h") and not re.search(r"#\s*define\s+vSemaphoreDelete\b|\bvoid\s+vSemaphoreDelete\s*\(",
                                                             open(SRC + "freertos/semphr.h", encoding="utf-8").read()):
    with open(SRC + "freertos/semphr.h", "a", encoding="utf-8") as f:
        f.write("\n// reader simulator: firmwares delete semaphores they no longer need; a no-op here\n"
                "#ifndef vSemaphoreDelete\ninline void vSemaphoreDelete(SemaphoreHandle_t) {}\n#endif\n")
# struct timeval: on the reader Arduino.h brings in sys/time.h, and firmwares rely on it (CrossPlant).
A = SRC + "Arduino.h"
if os.path.isfile(A) and "sys/time.h" not in open(A, encoding="utf-8").read():
    a = open(A, encoding="utf-8").read()
    at = a.find("#include")
    if at >= 0:
        open(A, "w", encoding="utf-8").write(a[:at] + "#include <sys/time.h>  // reader simulator: as on the reader\n" + a[at:])
# Setting the clock (CrossPoint 2.0): Emscripten declares settimeofday but has none; the simulator keeps the PC's
# clock. Weak, so a C library that has one keeps its own.
if os.path.isdir(SRC) and not os.path.isfile(SRC + "rsim_compat.cpp"):
    open(SRC + "rsim_compat.cpp", "w", encoding="utf-8").write(
        "// Added by the reader simulator (patch_libdeps.py): functions some firmwares need that this platform lacks.\n"
        "struct timeval;\nstruct timezone;\n"
        "extern \"C\" __attribute__((weak)) int settimeofday(const struct timeval *, const struct timezone *) { return 0; }\n")
# The newest library's link stubs name headers only the newest firmwares have (LcpLicense.h, Crypto.h,
# ContentProtection.h): an older firmware without them builds without that part.
LS = SRC + "firmware_link_stubs.cpp"
if os.path.isfile(LS):
    t = open(LS, encoding="utf-8").read()
    inc = "#include <ContentProtection.h>\n#include <Crypto.h>\n#include <LcpLicense.h>\n"
    end = "  err.clear();\n  return nullptr;\n}\n"
    if inc in t and "RSIM_HAS_LCP" not in t and t.count(end) == 1 and t.count("namespace freeink::content {") >= 1:
        guard = ("#if __has_include(<ContentProtection.h>) && __has_include(<Crypto.h>) && __has_include(<LcpLicense.h>)\n"
                 "#define RSIM_HAS_LCP 1\n" + inc + "#else\n#define RSIM_HAS_LCP 0\n#endif\n")
        t = t.replace(inc, guard)
        a = t.index("namespace freeink::content {")
        b = t.index(end) + len(end)
        t = t[:a] + "#if RSIM_HAS_LCP\n" + t[a:b] + "#endif  // RSIM_HAS_LCP\n" + t[b:]
        open(LS, "w", encoding="utf-8").write(t)
# Internet in the browser: the library fetches HTTP(S) with curl, which a web page cannot run. In the browser
# build the same requests go through the page's own connection (synchronous XMLHttpRequest, on the simulator's
# thread): servers that allow browser requests (CORS) answer, others fail as if offline. Nothing else changes:
# the Wi-Fi the firmware sees is the library's fake one, no password is needed or sent anywhere.
F = SRC + "SimHttpFetch.h"
if os.path.isfile(F) and "fetchWithBrowser" not in open(F, encoding="utf-8").read():
    t = open(F, encoding="utf-8").read()
    m = re.search(r"\n(inline bool fetch\(const std::string ?&)", t)
    r = re.search(r"\n(  return fetchWithCurl\([^;]*\);)\n", t[m.start():] if m else "")
    if m and r:
        browser = r'''
#ifdef __EMSCRIPTEN__
} // namespace sim_http_fetch
#include <emscripten.h>
namespace sim_http_fetch {
// reader simulator: HTTP(S) through the web page's connection (see patch_libdeps.py)
inline bool fetchWithBrowser(const std::string &url, const char *method,
                             const std::map<std::string, std::string> &headers,
                             const std::string &basicAuth, const char *body, Response &out) {
  std::string hdr;
  for (const auto &h : headers) hdr += h.first + "\n" + h.second + "\n";
  const int status = EM_ASM_INT({
    var x = new XMLHttpRequest();
    try {
      x.open(UTF8ToString($1), UTF8ToString($0), false);
      x.overrideMimeType('text/plain; charset=x-user-defined');
      var h = UTF8ToString($2).split('\n');
      for (var i = 0; i + 1 < h.length; i += 2) { try { x.setRequestHeader(h[i], h[i + 1]); } catch (e) {} }
      var a = UTF8ToString($3);
      if (a) x.setRequestHeader('Authorization', 'Basic ' + btoa(a));
      x.send($4 ? UTF8ToString($4) : null);
      globalThis.rsimHttpBody = x.responseText ? x.responseText : String();
      return x.status;
    } catch (e) { globalThis.rsimHttpBody = String(); return 0; }
  }, url.c_str(), method ? method : "GET", hdr.c_str(), basicAuth.c_str(), body);
  const int len = EM_ASM_INT({ return globalThis.rsimHttpBody.length; });
  out.body.assign(static_cast<size_t>(len), '\0');
  if (len > 0)
    EM_ASM({
      var s = globalThis.rsimHttpBody;
      for (var i = 0; i < s.length; i++) HEAPU8[$0 + i] = s.charCodeAt(i) & 255;
    }, &out.body[0]);
  EM_ASM({ globalThis.rsimHttpBody = String(); });
  out.statusCode = status;
  return status > 0;
}
#endif
'''
        a = m.start()
        t = t[:a] + browser + t[a:]
        m2 = re.search(r"\n(inline bool fetch\(const std::string ?&)", t)
        r2 = re.search(r"\n(  return fetchWithCurl\([^;]*\);)\n", t[m2.start():])
        at = m2.start() + r2.start(1)
        call = r2.group(1)
        t = (t[:at] + "#ifdef __EMSCRIPTEN__\n  return fetchWithBrowser(url, method, headers, basicAuth, body, out);\n#else\n"
             + call + "\n#endif" + t[at + len(call):])
        open(F, "w", encoding="utf-8").write(t)
    else:
        print("patch_libdeps: browser internet skipped, this library's fetch differs")
