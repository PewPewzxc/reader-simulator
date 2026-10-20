"""Browser-build fixes for the copied simulator library (work/.pio/libdeps/<env>).
Run after dev/sim-windows/patch_libdeps.py (frame, DRAG, battery env vars). Safe to run again."""
import os
import sys

L = sys.argv[1]


def patch(path, old, new):
    s = open(path, encoding="utf-8").read()
    if new in s:
        return
    if s.count(old) != 1:
        print("patch_work: skipped, text not found in", path)
        return
    open(path, "w", encoding="utf-8").write(s.replace(old, new))


# Emscripten is neither Linux nor Windows; take the OpenSSL path (compat/openssl/md5.h).
for name in ("MD5Builder.h", "MD5Builder_linux.h"):
    patch(L + "/simulator/src/" + name, "#elif defined(__linux__) || defined(_WIN32)\n",
          "#elif defined(__linux__) || defined(_WIN32) || defined(__EMSCRIPTEN__)\n")
# Sleep/wake and reboot relaunch the process (execvp), which a web page cannot do. Instead keep the
# simulator's CROSSPOINT_SIM_* / VARAGH_SIM_* variables in sessionStorage, save the SD card and reload
# the page; index.html puts the variables back before main() runs.
patch(L + "/simulator/src/SimulatorLifecycle.cpp", "[[noreturn]] void reexec() {\n",
      "[[noreturn]] void reexec() {\n"
      "#ifdef __EMSCRIPTEN__\n"
      "  std::string vars;\n"
      "  for (char **e = environ; *e; ++e)\n"
      "    if (!std::strncmp(*e, \"CROSSPOINT_SIM_\", 15) || !std::strncmp(*e, \"VARAGH_SIM_\", 11))\n"
      "      vars += std::string(*e) + \"\\n\";\n"
      "  MAIN_THREAD_EM_ASM({\n"
      "    sessionStorage.setItem('simRestartEnv', UTF8ToString($0));\n"
      "    FS.syncfs(false, () => location.reload());\n"
      "  }, vars.c_str());\n"
      "  for (;;) emscripten_is_main_browser_thread() ? emscripten_sleep(1000) : (void)sleep(1);  // until reload\n"
      "#endif\n")
patch(L + "/simulator/src/SimulatorLifecycle.cpp", "#include <unistd.h>\n",
      "#include <unistd.h>\n#ifdef __EMSCRIPTEN__\n#include <emscripten.h>\n#include <emscripten/threading.h>\n#include <string>\n#endif\n")
# Asleep, only keyboard keys woke the reader; a click on a frame key (POWER, HOME, ...) now wakes it too.
# (Same gap in the Windows build: dev/sim-windows/patch_libdeps.py could take this fix.)
patch(L + "/simulator/src/HalGPIO.cpp",
      "        SimulatorLifecycle::rebootAsPowerWake();\n      }\n    }\n\n    SDL_Delay(10);",
      "        SimulatorLifecycle::rebootAsPowerWake();\n      }\n"
      "      if (simFrameActive() && e.type == SDL_MOUSEBUTTONDOWN && e.button.button == SDL_BUTTON_LEFT) {\n"
      "        float nx = 0, ny = 0;\n"
      "        const std::string hit = simFrameHit(e.button.x, e.button.y, &nx, &ny);\n"
      "        if (!hit.empty() && hit != \"SCREEN\") {\n"
      "          clearButtonState();\n"
      "          SimulatorLifecycle::rebootAsPowerWake();\n"
      "        }\n"
      "      }\n    }\n\n    SDL_Delay(10);")
# fsync on IndexedDB storage is an async JS call proxied to the page's main thread; when the main thread
# waits for the render lock that the syncing task holds, both wait for ever (the book reader froze).
# Files live in memory until the page saves the SD card (every 5 s, and before a reload), so skip it.
patch(L + "/simulator/src/HalStorage.cpp", "#include <vector>\n",
      "#include <vector>\n#ifdef __EMSCRIPTEN__\n#define fsync(fd) 0\n#endif\n")
# Older simulator library (crosspoint-simulator): no reexec(); rebootAsPowerWake() calls execvp itself.
LC = L + "/simulator/src/SimulatorLifecycle.cpp"
if os.path.isfile(LC) and "void reexec()" not in open(LC, encoding="utf-8").read():
    patch(LC, "  execvp(gArgv[0], gArgv);\n",
          "#ifdef __EMSCRIPTEN__\n"
          "  {\n"
          "    std::string vars;\n"
          "    for (char **e = environ; *e; ++e)\n"
          "      if (!std::strncmp(*e, \"CROSSPOINT_SIM_\", 15) || !std::strncmp(*e, \"VARAGH_SIM_\", 11))\n"
          "        vars += std::string(*e) + \"\\n\";\n"
          "    MAIN_THREAD_EM_ASM({\n"
          "      sessionStorage.setItem('simRestartEnv', UTF8ToString($0));\n"
          "      FS.syncfs(false, () => location.reload());\n"
          "    }, vars.c_str());\n"
          "    for (;;) emscripten_is_main_browser_thread() ? emscripten_sleep(1000) : (void)sleep(1);  // until reload\n"
          "  }\n"
          "#endif\n"
          "  execvp(gArgv[0], gArgv);\n")
