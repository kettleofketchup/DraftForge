#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="$ROOT/app/components/navbar"

# Match these props with any quoted literal of 3+ chars.
# Translated values use JSX brace syntax ({t(...)}), so quoted literals here
# are by construction untranslated strings.
PATTERN='(title|subtitle|label|placeholder|tooltip|description)="[^"]{3,}"'

if grep -rEn "$PATTERN" "$TARGET" --include='*.tsx' --include='*.ts'; then
  echo ""
  echo "ERROR: Untranslated visible prop strings in navbar/."
  echo "Wrap each match with t('<key>') and add the key to:"
  echo "  app/i18n/locales/en/navbar.json"
  echo "  app/i18n/locales/es/navbar.json"
  exit 1
fi

echo "OK: no untranslated visible prop strings in navbar/."
