#!/usr/bin/env bash
set -uo pipefail
gate="$(dirname "$0")/frontend-screenshot-gate.sh"
fail=0

expect() {
  local want=$1 path=$2 got=1
  "$gate" "$path" >/dev/null && got=0
  if [ "$got" != "$want" ]; then
    echo "FAIL: $path expected exit $want, got $got"
    fail=1
  fi
}

for p in \
  frontend/app/components/ui/button.tsx \
  frontend/app/routes/home.tsx \
  frontend/app/features/events/api.ts \
  frontend/app/lib/logger.ts \
  frontend/app/store/user.ts \
  frontend/app/hooks/useThing.ts \
  frontend/app/app.css \
  frontend/app/i18n/en.json \
  frontend/public/favicon.ico \
  frontend/package.json \
  frontend/vite.config.ts \
  frontend/tailwind.config.js; do
  expect 0 "$p"
done

for p in \
  frontend/tests/playwright/e2e/navigation.spec.ts \
  frontend/tests/unit/foo.test.ts \
  frontend/app/components/ui/button.test.tsx \
  frontend/app/features/events/__tests__/api.test.ts \
  frontend/app/lib/__mocks__/api.ts \
  frontend/app/test-utils/render.tsx \
  frontend/vitest.config.ts \
  frontend/vitest.setup.ts \
  frontend/playwright.config.ts \
  frontend/playwright.demo.config.ts \
  frontend/Dockerfile.playwright \
  frontend/README.md \
  backend/app/models.py \
  docs/index.md; do
  expect 1 "$p"
done

out=$(printf '%s\n' backend/x.py frontend/app/lib/a.ts frontend/tests/b.spec.ts | "$gate")
[ "$out" = "frontend/app/lib/a.ts" ] || { echo "FAIL: stdin mode printed '$out'"; fail=1; }

mixed=$(printf '%s\n' \
  frontend/app/components/events/DiscordConfigSection.tsx \
  frontend/app/components/events/__tests__/DiscordConfigSection.test.tsx \
  frontend/app/features/events/settingsFields.ts \
  frontend/app/features/events/__tests__/settingsFields.test.ts | "$gate")
want=$(printf '%s\n' frontend/app/components/events/DiscordConfigSection.tsx frontend/app/features/events/settingsFields.ts)
[ "$mixed" = "$want" ] || { echo "FAIL: mixed component + __tests__ diff printed '$mixed'"; fail=1; }

printf '%s\n' \
  frontend/app/components/events/__tests__/DiscordConfigSection.test.tsx \
  frontend/app/features/events/__tests__/settingsFields.test.ts \
  frontend/tests/playwright/e2e/events.spec.ts | "$gate" >/dev/null && { echo "FAIL: tests-only diff should exit 1"; fail=1; }

printf '' | "$gate" >/dev/null && { echo "FAIL: empty input should exit 1"; fail=1; }

[ "$fail" = 0 ] && echo "ok"
exit "$fail"
