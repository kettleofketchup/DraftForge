#!/usr/bin/env bash
# Print changed non-test frontend files; exit 0 when screenshots are required, 1 when not.
# Usage: frontend-screenshot-gate.sh [file...]   (reads newline-separated paths from stdin when no args)
#   gh pr diff "$PR" --name-only | frontend-screenshot-gate.sh
#   git diff --name-only origin/main...HEAD | frontend-screenshot-gate.sh
set -euo pipefail

test_paths='(^frontend/tests/|/__tests__/|/__mocks__/|^frontend/app/test-utils/|\.(test|spec)\.[cm]?[jt]sx?$|^frontend/(vitest|playwright)[^/]*\.[cm]?[jt]s$|^frontend/Dockerfile\.(playwright|cypress)$|^frontend/screenshots/|\.md$)'

if [ "$#" -gt 0 ]; then
  printf '%s\n' "$@"
else
  cat
fi | grep -E '^frontend/' | grep -vE "$test_paths" || exit 1
