#!/usr/bin/env bash
# Usage: shadcn-lint-files.sh <repo-relative paths...>
# Runs the @shadcn/lint gate (eslint.shadcn.config.js) on the given frontend/app
# sources; other paths are skipped. A change to the config or the suppressions
# baseline lints all of app/ instead.
set -euo pipefail

FRONTEND="$(cd "$(dirname "$0")/.." && pwd)"
ESLINT="$FRONTEND/node_modules/.bin/eslint"
CONFIG=eslint.shadcn.config.js
SUPPRESSIONS=shadcn-lint-suppressions.json

files=()
full=0
for path in "$@"; do
  case "$path" in
    "frontend/$CONFIG" | "frontend/$SUPPRESSIONS") full=1 ;;
    frontend/app/*.js | frontend/app/*.jsx | frontend/app/*.ts | frontend/app/*.tsx)
      files+=("${path#frontend/}") ;;
  esac
done
[[ $full -eq 1 ]] && files=(app)
[[ ${#files[@]} -eq 0 ]] && exit 0

if [[ ! -x "$ESLINT" ]]; then
  echo "eslint not installed: run 'npm --prefix frontend ci'" >&2
  exit 1
fi

cd "$FRONTEND"
if ! "$ESLINT" -c "$CONFIG" --suppressions-location "$SUPPRESSIONS" "${files[@]}"; then
  echo "shadcn-lint failed. Fixed a baselined violation? Run 'just frontend::lint-shadcn-prune' and commit $SUPPRESSIONS." >&2
  exit 1
fi
