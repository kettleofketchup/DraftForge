#!/usr/bin/env bash
# Usage: prettier-check-files.sh [--write] <paths...>
# Runs prettier from frontend/ (plugins resolve from frontend/node_modules) on the
# given paths. Paths may be absolute, relative to the CWD, or repo-relative; paths
# outside frontend/ are skipped with a warning, and the script exits 1 if every
# given path was skipped.
set -euo pipefail

FRONTEND="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(dirname "$FRONTEND")"
PRETTIER="$FRONTEND/node_modules/.bin/prettier"

mode=--check
if [[ "${1:-}" == "--write" ]]; then
  mode=--write
  shift
fi

files=()
for path in "$@"; do
  abs="$(realpath -m -- "$path")"
  if [[ "$abs" != "$FRONTEND"/* && "$path" != /* ]]; then
    abs="$(realpath -m -- "$ROOT/$path")"
  fi
  if [[ "$abs" == "$FRONTEND"/* ]]; then
    files+=("${abs#"$FRONTEND"/}")
  else
    echo "prettier-check-files: skipping $path (outside frontend/)" >&2
  fi
done
if [[ ${#files[@]} -eq 0 ]]; then
  [[ $# -eq 0 ]] && exit 0
  echo "prettier-check-files: no frontend/ files to check" >&2
  exit 1
fi

if [[ ! -x "$PRETTIER" ]]; then
  echo "prettier not installed: run 'npm --prefix frontend ci'" >&2
  exit 1
fi

cd "$FRONTEND"
"$PRETTIER" "$mode" --ignore-unknown "${files[@]}"
