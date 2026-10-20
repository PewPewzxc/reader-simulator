#!/bin/bash
# Download one firmware version from GitHub, build one simulator model, take a home-screen picture.
#   tools/try_firmware.sh <owner/repo> [ref] [env]     (ref: release tag or branch; default: newest release)
# Prints one result line: OK / BUILD FAILED / RUN FAILED, with where the log or picture is.
O="$(cd "$(dirname "$0")/.." && pwd)"
repo="$1"; ref="$2"; env="${3:-}"
PY="$HOME/.platformio/penv/Scripts/python.exe"
L="import sys; sys.path.insert(0, r'$(cygpath -w "$O")'); import launcher"
[ -n "$ref" ] || ref=$("$PY" -I -c "$L; print(launcher.versions('$repo')[0])" | tr -d '\r')
folder=$("$PY" -I "$O/tools/fetch.py" "$repo" "$ref" 2>&1 | tail -1)
[ -f "$folder/platformio.ini" ] || { echo "$repo $ref: DOWNLOAD FAILED: $folder"; exit 1; }
if [ -z "$env" ]; then  # first simulator env this firmware has, X4 Pro first
  env=$("$PY" -I -c "$L; e=launcher.envs_for(r'$folder'); print((e.get('X4 Pro') or e.get('X4 Classic') or e.get('X3') or ''))")
fi
[ -n "$env" ] || { echo "$repo: NO SIMULATOR SETUP"; exit 1; }
name=$(tr '/@' '--' < "$folder/.rsim-name" | tr -d '\r\n'); log="$O/logs/$name-$env.log"; mkdir -p "$O/logs"
if ! bash "$O/build.sh" "$folder" "$env" > "$log" 2>&1; then
  echo "$name $env: BUILD FAILED ($(grep -m1 -E 'error:|cannot find|FAILED' "$log" | cut -c1-150)) log: $log"; exit 1
fi
# Keep this model's build: PlatformIO empties every .pio/build/<env> when the project config changes
# (pin_simlib.py adds a block per model), so the next model's build would delete it.
out="$folder/.rsim-out/$env"; rm -rf "$out"; mkdir -p "$out"
cp -f "$folder/.pio/build/$env/program.exe" "$folder/.pio/build/$env/"*.dll "$out/"
frame=$("$PY" -I -c "$L
m=[k for k,v in launcher.envs_for(r'$folder').items() if v=='$env'][0]; print(launcher.MODELS[m])")
export CROSSPOINT_SIM_FRAME=$(cygpath -m "$O/../device-frames/frames/$frame")
shots="$O/logs/$name-$env"  # own folder per run, so several runs can go at once
rm -f "$shots"/home.*
SIM_SRC="$folder" SIM_ENV="$env" SIM_CARD="$O/cards/try-$name-$env" SIM_SHOTS="$shots" \
  bash "$O/sim.sh" '6000:QUIT' "5000:home" > /dev/null
pic=$(ls "$shots"/home.png "$shots"/home.bmp 2>/dev/null | head -1)  # .bmp where there is no ffmpeg (CI)
if [ -n "$pic" ]; then
  echo "$name $env: OK ($(grep -c 'SIM FRAME\] using' "$shots/last-run.log") frame) picture: $pic"
else
  echo "$name $env: RUN FAILED log: $shots/last-run.log"; exit 1
fi
