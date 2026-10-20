#!/bin/bash
# Run the Windows simulator windowless and save PNG screenshots.
#   ./sim.sh '<input script>' '<ms>:<name>;<ms>:<name>...'
# Input: TAP:x,y[,holdMs]  SWIPE:x1,y1,x2,y2[,ms]  BACK ENTER LEFT RIGHT UP DOWN HOME POWER SLEEP QUIT
# Runs the firmware build.sh built last (or SIM_SRC=<folder> SIM_ENV=<env>).
# Each firmware gets its own SD card, cards/<folder name>/fs_/, and pictures in
# cards/<folder name>/shots/ (or SIM_CARD / SIM_SHOTS).
O="$(cd "$(dirname "$0")" && pwd)"
{ read -r lastSrc; read -r lastEnv; } < "$O/.last-firmware" 2>/dev/null
SRC="${SIM_SRC:-$lastSrc}"; ENV="${SIM_ENV:-${lastEnv:-x4-pro-simulator}}"
[ -n "$SRC" ] || { echo "nothing built yet: run build.sh <firmware folder>"; exit 1; }
PROGRAM="$SRC/.pio/build/$ENV/program.exe"
card="${SIM_CARD:-$O/cards/$(basename "$SRC")}"; out="${SIM_SHOTS:-$card/shots}"
mkdir -p "$card" "$out"
[ -x "$PROGRAM" ] || { echo "not built: run build.sh first"; exit 1; }
outRel="$(realpath --relative-to="$card" "$out")"  # the simulator splits on ':', so no C:/ paths

shots=""; names=()
IFS=';' read -ra items <<< "$2"
for it in "${items[@]}"; do
  [ -n "$it" ] || continue
  shots+="${it%%:*}:$outRel/${it#*:}.bmp;"; names+=("${it#*:}")
done

cd "$card"
SDL_VIDEODRIVER=dummy SDL_RENDER_DRIVER=software SDL_AUDIODRIVER=dummy \
CROSSPOINT_SIM_INPUT_SCRIPT="$1" CROSSPOINT_SIM_SCREENSHOTS="${shots%;}" \
  timeout "${SIM_TIMEOUT:-120}" "$PROGRAM" > "$out/last-run.log" 2>&1
echo "exit=$?"
for n in "${names[@]}"; do
  if [ -f "$out/$n.bmp" ] && ! command -v ffmpeg > /dev/null; then
    echo "saved $out/$n.bmp (no ffmpeg for PNG)"
  elif [ -f "$out/$n.bmp" ]; then
    ffmpeg -loglevel error -y -i "$out/$n.bmp" -pix_fmt gray "$out/$n.png" && rm -f "$out/$n.bmp" && echo "saved $out/$n.png"
  else
    echo "MISSING $n"
  fi
done
