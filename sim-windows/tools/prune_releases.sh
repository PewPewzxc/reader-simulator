#!/usr/bin/env bash
# Deletes the releases (and their tags) whose tag starts with <prefix> and that <list.json> no longer points at,
# so only the builds still offered stay on the Releases page.
#   bash prune_releases.sh <prefix> <list.json>      (needs GH_TOKEN and REPO)
set -euo pipefail
prefix=$1; list=$2
for tag in $(gh release list --repo "$REPO" --limit 200 --json tagName --jq ".[].tagName | select(startswith(\"$prefix\"))"); do
  if grep -q "/download/$tag/\|\"release\": *\"$tag\"" "$list"; then
    echo "kept $tag"
  else
    gh release delete "$tag" --repo "$REPO" --cleanup-tag --yes && echo "deleted $tag"
  fi
done
