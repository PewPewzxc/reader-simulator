#include "SimulatorDeviceFrame.h"

#include <HalDisplay.h>

#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <map>

#include "stb_image.h"

namespace {
struct Rect {
  int x = 0, y = 0, w = 0, h = 0;
  bool contains(int px, int py) const { return px >= x && py >= y && px < x + w && py < y + h; }
};

bool loaded = false, active = false;
int frameW = 0, frameH = 0;
Rect screen;
std::map<std::string, Rect> keys;
unsigned char *pixels = nullptr;  // RGBA, until the texture exists
SDL_Texture *frameTex = nullptr, *deviceTex = nullptr;
std::string pressed;
std::atomic<bool> redraw{false};
int lastAngle = 0, lastWindowW = 0, lastWindowH = 0;

void load() {
  if (loaded) return;
  loaded = true;
  const char *base = std::getenv("CROSSPOINT_SIM_FRAME");
  if (!base || !*base) return;
  FILE *f = std::fopen((std::string(base) + ".keys").c_str(), "r");
  if (!f) {
    std::cerr << "[SIM FRAME] no " << base << ".keys, running without a frame" << std::endl;
    return;
  }
  char word[16], name[16];
  Rect r;
  while (std::fscanf(f, "%15s", word) == 1) {
    if (!std::strcmp(word, "size")) {
      std::fscanf(f, "%d %d", &frameW, &frameH);
    } else if (!std::strcmp(word, "screen")) {
      std::fscanf(f, "%d %d %d %d", &screen.x, &screen.y, &screen.w, &screen.h);
    } else if (!std::strcmp(word, "key") && std::fscanf(f, "%15s %d %d %d %d", name, &r.x, &r.y, &r.w, &r.h) == 5) {
      keys[name] = r;
    }
  }
  std::fclose(f);
  int w = 0, h = 0, n = 0;
  pixels = stbi_load((std::string(base) + ".png").c_str(), &w, &h, &n, 4);
  // The frame's screen hole must be exactly the visible panel, or touches would land in the wrong place.
  const int visibleLong = HalDisplay::DISPLAY_WIDTH - 4, visibleShort = HalDisplay::DISPLAY_HEIGHT - 4;
  if (!pixels || w != frameW || h != frameH || screen.w != visibleShort || screen.h != visibleLong) {
    std::cerr << "[SIM FRAME] " << base << " does not fit this device (" << screen.w << "x" << screen.h
              << " screen, panel needs " << visibleShort << "x" << visibleLong << "); running without a frame"
              << std::endl;
    if (pixels) stbi_image_free(pixels);
    pixels = nullptr;
    return;
  }
  active = true;
  std::cerr << "[SIM FRAME] using " << base << " (" << frameW << "x" << frameH << ", " << keys.size() << " keys)"
            << std::endl;
}

// Window point -> point on the upright device picture (inverse of the turn).
void windowToDevice(int x, int y, int *dx, int *dy) {
  const int cx = x - lastWindowW / 2, cy = y - lastWindowH / 2;
  int ux = cx, uy = cy;
  switch (lastAngle) {
    case 90: ux = cy, uy = -cx; break;
    case 180: ux = -cx, uy = -cy; break;
    case 270: ux = -cy, uy = cx; break;
    default: break;
  }
  *dx = ux + frameW / 2;
  *dy = uy + frameH / 2;
}
}  // namespace

bool simFrameActive() {
  load();
  return active;
}

void simFrameWindowSize(bool portrait, int *w, int *h) {
  *w = portrait ? frameW : frameH;
  *h = portrait ? frameH : frameW;
}

void simFrameRender(SDL_Renderer *renderer, SDL_Texture *panel, const SDL_Rect &src, int deviceAngle, int windowW,
                    int windowH) {
  if (!frameTex) {
    frameTex = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_ABGR8888, SDL_TEXTUREACCESS_STATIC, frameW, frameH);
    SDL_UpdateTexture(frameTex, nullptr, pixels, frameW * 4);
    SDL_SetTextureBlendMode(frameTex, SDL_BLENDMODE_BLEND);
    stbi_image_free(pixels);
    pixels = nullptr;
    deviceTex = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_ARGB8888, SDL_TEXTUREACCESS_TARGET, frameW, frameH);
    SDL_SetTextureBlendMode(deviceTex, SDL_BLENDMODE_BLEND);
  }
  lastAngle = deviceAngle, lastWindowW = windowW, lastWindowH = windowH;

  // 1. the upright reader: panel turned into portrait (as the Portrait orientation does), frame on top
  SDL_SetRenderTarget(renderer, deviceTex);
  SDL_SetRenderDrawColor(renderer, 0, 0, 0, 0);
  SDL_RenderClear(renderer);
  const SDL_Rect panelDst = {screen.x + (screen.w - src.w) / 2, screen.y + (screen.h - src.h) / 2, src.w, src.h};
  SDL_RenderCopyEx(renderer, panel, &src, &panelDst, 90.0, nullptr, SDL_FLIP_NONE);
  SDL_RenderCopy(renderer, frameTex, nullptr, nullptr);
  auto key = keys.find(pressed);
  if (key != keys.end()) {
    const SDL_Rect r = {key->second.x, key->second.y, key->second.w, key->second.h};
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    SDL_SetRenderDrawColor(renderer, 255, 255, 255, 50);
    SDL_RenderFillRect(renderer, &r);
  }

  // 2. the reader into the window, turned the way the firmware holds it
  SDL_SetRenderTarget(renderer, nullptr);
  SDL_SetRenderDrawColor(renderer, 236, 235, 230, 255);  // light desk behind the reader
  SDL_RenderClear(renderer);
  const SDL_Rect dst = {(windowW - frameW) / 2, (windowH - frameH) / 2, frameW, frameH};
  SDL_RenderCopyEx(renderer, deviceTex, nullptr, &dst, deviceAngle, nullptr, SDL_FLIP_NONE);
}

std::string simFrameHit(int windowX, int windowY, float *panelNx, float *panelNy) {
  int x = 0, y = 0;
  windowToDevice(windowX, windowY, &x, &y);
  for (const auto &k : keys)
    if (k.second.contains(x, y)) return k.first;
  if (!screen.contains(x, y)) return "";
  // upright screen point -> panel pixel (the Portrait mapping, 2 px bezel inset)
  const int panelX = (y - screen.y) + 2;
  const int panelY = HalDisplay::DISPLAY_HEIGHT - 1 - ((x - screen.x) + 2);
  *panelNx = static_cast<float>(panelX) / (HalDisplay::DISPLAY_WIDTH - 1);
  *panelNy = static_cast<float>(panelY) / (HalDisplay::DISPLAY_HEIGHT - 1);
  return "SCREEN";
}

void simFrameSetPressed(const std::string &key) {
  if (key == pressed) return;
  pressed = key;
  redraw.store(true);
}

bool simFrameTakeRedraw() { return redraw.exchange(false); }
