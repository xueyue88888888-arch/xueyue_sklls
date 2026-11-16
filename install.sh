#!/usr/bin/env bash
# Sync every skill in this repo into the local Alma skills directory.
#   ./install.sh                 # all skills
#   ./install.sh <skill-name>    # one skill
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${ALMA_SKILLS_DIR:-$HOME/.config/alma/skills}"
ONLY="${1:-}"
mkdir -p "$DEST"

found=0
for dir in "$ROOT"/*/; do
  name="$(basename "$dir")"
  case "$name" in .git|.github|node_modules) continue;; esac
  [ -f "$dir/SKILL.md" ] || continue
  [ -n "$ONLY" ] && [ "$name" != "$ONLY" ] && continue
  found=1
  if [ ! -d "$DEST/$name" ]; then
    alma skill create "$name" --file "$dir/SKILL.md" >/dev/null
    echo "registered $name"
  fi
  for item in scripts references examples README.md; do
    [ -e "$dir/$item" ] && cp -R "$dir/$item" "$DEST/$name/"
  done
  cp "$dir/SKILL.md" "$DEST/$name/SKILL.md"
  echo "synced     $name -> $DEST/$name"
done

[ "$found" = 1 ] || { echo "no skills found"; exit 1; }
