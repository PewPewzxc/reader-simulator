#!/bin/bash
# Try every model of each firmware version listed on stdin ("owner/repo<TAB>ref" lines, from latest_refs.py;
# an optional third column names one env to try instead of all of them).
#   python -I tools/latest_refs.py | tools/try_all.sh [parallel jobs, default 3]
# Appends "repo<TAB>ref<TAB>env<TAB>OK|BUILD FAILED|RUN FAILED|...<TAB>detail" lines to logs/results.tsv.
# Models of one firmware run one after another (they share the folder); firmwares run side by side.
O="$(cd "$(dirname "$0")/.." && pwd)"
PY="$HOME/.platformio/penv/Scripts/python.exe"
jobs="${1:-3}"
one() {
  local repo="$1" ref="$2" only="$3" folder envs env line
  folder=$("$PY" -I "$O/tools/fetch.py" "$repo" "$ref" 2>&1 | tail -1)
  envs=$("$PY" -I -c "import sys; sys.path.insert(0, r'$(cygpath -w "$O")'); import launcher
print(' '.join(launcher.envs_for(r'$folder').values()))")
  [ -z "$only" ] || envs="$only"
  [ -n "$envs" ] || { printf '%s\t%s\t-\tNO SIMULATOR SETUP\t%s\n' "$repo" "$ref" "$folder" >> "$O/logs/results.tsv"; return; }
  for env in $envs; do
    line=$(bash "$O/tools/try_firmware.sh" "$repo" "$ref" "$env" 2>&1 | tail -1)
    printf '%s\t%s\t%s\t%s\t%s\n' "$repo" "$ref" "$env" "$(sed -E 's/^[^:]*: ([A-Z ]+).*/\1/' <<< "$line" | sed 's/ *$//')" "$line" >> "$O/logs/results.tsv"
  done
}
mkdir -p "$O/logs"
while IFS=$'\t' read -r repo ref only; do
  [ -n "$repo" ] || continue
  while [ "$(jobs -rp | wc -l)" -ge "$jobs" ]; do wait -n; done
  one "$repo" "$ref" "$only" < /dev/null &  # children must not eat the list on stdin
done < <(tr -d '\r')  # lines from Windows Python end in CR
wait
