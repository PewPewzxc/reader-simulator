#pragma once
// Device frame around the simulator screen: a picture of the real reader with
// clickable physical keys. Off unless CROSSPOINT_SIM_FRAME=<dir>/<model> names
// a frame (<model>.png + <model>.keys from dev/device-frames).
// CROSSPOINT_SIM_SCALE=<factor> draws it bigger or smaller (Real size). Added to the
// simulator library by dev/sim-windows/patch_libdeps.py.
#include <SDL.h>

#include <string>

// Reads the frame files once; true when a frame is in use.
bool simFrameActive();
// Window size for the frame, turned for landscape orientations.
void simFrameWindowSize(bool portrait, int *w, int *h);
// Draws panel (the visible part `src` of the panel texture) and frame into the
// window. deviceAngle: how far the reader is turned (0, 90, 180, 270 clockwise).
void simFrameRender(SDL_Renderer *renderer, SDL_Texture *panel, const SDL_Rect &src, int deviceAngle,
                    int windowW, int windowH);
// Window point -> what is there: a key name ("UP", "HOME", ...), "SCREEN" with
// the point in panel-normalised coordinates, or "" for nothing.
std::string simFrameHit(int windowX, int windowY, float *panelNx, float *panelNy);
// Shows a key as pressed ("" for none) and asks for a redraw.
void simFrameSetPressed(const std::string &key);
// Asks for one redraw (e.g. Windows repainting the sleeping reader's window).
void simFrameRequestRedraw();
// True once after something on the frame changed.
bool simFrameTakeRedraw();
