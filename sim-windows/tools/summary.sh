#!/bin/bash
# Last result of every (firmware, model) in logs/results.tsv, with the first error line of failed builds.
#   tools/summary.sh
O="$(cd "$(dirname "$0")/.." && pwd)"
awk -F'\t' '$3 != "-" {last[$1 "\t" $3] = $0} END {for (k in last) print last[k]}' "$O/logs/results.tsv" | sort |
while IFS=$'\t' read -r repo ref env status line; do
  why=""
  if [ "$status" != OK ]; then
    log=$(grep -oE 'log: [^ ]+' <<< "$line" | cut -c6-)
    if [ ! -s "$log" ]; then why="(empty log)"
    else why=$(grep -m1 -E 'error:|Error [0-9]|Exception|WinError|cannot find|undefined reference' "$log" | cut -c1-160); fi
  fi
  printf '%-32s %-28s %-22s %-13s %s\n' "$repo" "$ref" "$env" "$status" "$why"
done
