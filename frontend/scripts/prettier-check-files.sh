#!/usr/bin/env bash
# Usage: prettier-check-files.sh [--write] <repo-relative paths...>
# Runs prettier from frontend/ (plugins resolve from frontend/node_modules) on the
# given frontend/ paths; other paths are skipped.
set -euo pipefail

FRONTEND="$(cd "$(dirname "$0")/.." && pwd)"
PRETTIER="$FRONTEND/node_modules/.bin/prettier"

mode=--check
if [[ "${1:-}" == "--write" ]]; then
  mode=--write
  shift
fi

files=()
for path in "$@"; do
  [[ "$path" == frontend/* ]] && files+=("${path#frontend/}")
done
[[ ${#files[@]} -eq 0 ]] && exit 0

if [[ ! -x "$PRETTIER" ]]; then
  echo "prettier not installed: run 'npm --prefix frontend ci'" >&2
  exit 1
fi

cd "$FRONTEND"
"$PRETTIER" "$mode" --ignore-unknown "${files[@]}"
