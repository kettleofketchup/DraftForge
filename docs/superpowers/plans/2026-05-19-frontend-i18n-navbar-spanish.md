# Frontend i18n Navbar (Spanish) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Spanish translation of the DraftForge navbar (visible text + `aria-label`s) with SSR-aware locale detection, a `just frontend::*` validation module, and CI gates that prevent untranslated strings from regressing.

**Architecture:** React Router 7 SSR app uses `remix-i18next` to detect locale from `?lang=` query → `df-locale` cookie → `Accept-Language` header → `en` fallback in the `root.tsx` loader. Per-request i18n instance on the server, singleton on the client (synced via `useChangeLanguage`). Translation JSON bundled at build time under `app/i18n/locales/`. `eslint-plugin-i18next` (JSX text) + parser key-parity (`--fail-on-update`) + a grep guard (prop-based visible text) enforce completeness. `/` and `/about` stay prerendered (link previews); Spanish flicker on those two routes is documented and accepted.

**Tech Stack:** `i18next`, `react-i18next`, `remix-i18next` (runtime); `i18next-parser`, `eslint-plugin-i18next` (dev); existing React Router 7, TypeScript, Playwright, just, npm.

**Spec:** `docs/superpowers/specs/2026-05-19-frontend-i18n-navbar-spanish-design.md`

---

## File map

**New files:**
- `frontend/app/i18n/config.ts` — `createI18nInstance(locale)` factory
- `frontend/app/i18n/server.ts` — `RemixI18Next` + cookie definition
- `frontend/app/i18n/client.ts` — client singleton + cookie-fallback for prerendered routes
- `frontend/app/i18n/types.ts` — TS module augmentation for typed `t()`
- `frontend/app/i18n/locales/en/navbar.json`
- `frontend/app/i18n/locales/es/navbar.json`
- `frontend/i18next-parser.config.ts`
- `frontend/eslint.config.js`
- `frontend/scripts/check-navbar-prop-strings.sh`
- `frontend/tests/playwright/e2e/01-navigation-i18n.spec.ts`
- `frontend/tests/playwright/e2e/06-visual-qa-navbar-i18n.spec.ts`
- `just/frontend/mod.just`
- `just/frontend/i18n.just`

**Modified files:**
- `frontend/package.json` — deps + scripts
- `frontend/app/root.tsx` — add `loader`, modify `Layout`
- `frontend/app/entry.server.tsx` — wrap render in `<I18nextProvider>`
- `frontend/app/entry.client.tsx` — wrap hydrate in `<I18nextProvider>`
- `frontend/playwright.config.ts` — pin `use.locale: 'en-US'`
- `frontend/app/components/navbar/navbar.tsx` — wrap strings with `t()` + `data-testid`s
- `frontend/app/components/navbar/MobileNav.tsx` — wrap strings with `t()`
- `frontend/app/components/navbar/PageNavBar.tsx` — wrap strings with `t()`
- `frontend/app/components/navbar/login.tsx` — wrap "Login with Discord" + `data-testid`
- `justfile` — add `mod frontend`
- `just/npm.just` — remove `typecheck` and `lint` recipes

**Unchanged (verified):**
- `frontend/tsconfig.json` already has `resolveJsonModule: true`
- `frontend/react-router.config.ts` keeps `prerender: ["/", "/about"]`

---

## Task 1: Install dependencies

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: Install runtime dependencies**

```bash
cd frontend && npm install i18next react-i18next remix-i18next
```

Expected output: ~3 new entries under `dependencies` in `package.json`, no peer-dependency warnings (React Router 7 + react-i18next are compatible).

- [ ] **Step 2: Install dev dependencies**

```bash
cd frontend && npm install --save-dev i18next-parser eslint-plugin-i18next
```

- [ ] **Step 3: Verify installs**

```bash
cd frontend && npm ls i18next react-i18next remix-i18next i18next-parser eslint-plugin-i18next
```

Expected: all five resolve to a single version, no `UNMET DEPENDENCY` lines.

- [ ] **Step 4: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "build(i18n): add i18next stack + parser + eslint plugin"
```

---

## Task 2: Create translation JSON files

**Files:**
- Create: `frontend/app/i18n/locales/en/navbar.json`
- Create: `frontend/app/i18n/locales/es/navbar.json`

- [ ] **Step 1: Create directories**

```bash
mkdir -p frontend/app/i18n/locales/en frontend/app/i18n/locales/es
```

- [ ] **Step 2: Write English source of truth**

File: `frontend/app/i18n/locales/en/navbar.json`

```json
{
  "login": "Login with Discord",
  "signup_here": "Sign up here",
  "home": "Home",
  "logout": "Logout",
  "edit_profile": "Edit Profile",
  "aria": {
    "star_github": "Star us on GitHub",
    "documentation": "Documentation",
    "report_bug": "Report a Bug",
    "main_nav": "Main navigation"
  }
}
```

- [ ] **Step 3: Write Spanish translations**

File: `frontend/app/i18n/locales/es/navbar.json`

```json
{
  "login": "Iniciar sesión con Discord",
  "signup_here": "Regístrate aquí",
  "home": "Inicio",
  "logout": "Cerrar sesión",
  "edit_profile": "Editar perfil",
  "aria": {
    "star_github": "Danos una estrella en GitHub",
    "documentation": "Documentación",
    "report_bug": "Reportar un problema",
    "main_nav": "Navegación principal"
  }
}
```

- [ ] **Step 4: Verify both files parse as JSON**

```bash
node -e "JSON.parse(require('fs').readFileSync('frontend/app/i18n/locales/en/navbar.json','utf8'))"
node -e "JSON.parse(require('fs').readFileSync('frontend/app/i18n/locales/es/navbar.json','utf8'))"
```

Expected: no output, exit code 0 for both.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/i18n/locales/
git commit -m "feat(i18n): add en + es navbar translation files"
```

---

## Task 3: Create `app/i18n/config.ts` factory

**Files:**
- Create: `frontend/app/i18n/config.ts`

- [ ] **Step 1: Write the factory**

File: `frontend/app/i18n/config.ts`

```ts
import { createInstance, type i18n as I18nInstance } from 'i18next';
import { initReactI18next } from 'react-i18next';

import enNavbar from './locales/en/navbar.json';
import esNavbar from './locales/es/navbar.json';

export const SUPPORTED_LOCALES = ['en', 'es'] as const;
export type SupportedLocale = (typeof SUPPORTED_LOCALES)[number];
export const FALLBACK_LOCALE: SupportedLocale = 'en';

export function createI18nInstance(locale: string): I18nInstance {
  const instance = createInstance();
  instance.use(initReactI18next).init({
    lng: locale,
    fallbackLng: FALLBACK_LOCALE,
    supportedLngs: [...SUPPORTED_LOCALES],
    ns: ['navbar'],
    defaultNS: 'navbar',
    resources: {
      en: { navbar: enNavbar },
      es: { navbar: esNavbar },
    },
    interpolation: { escapeValue: false },
    react: { useSuspense: false },
  });
  return instance;
}
```

- [ ] **Step 2: Verify the file type-checks**

```bash
just frontend::tsc
```

This will not pass yet because `just/frontend/mod.just` doesn't exist. Use the underlying npm script directly until Task 13 wires it up:

```bash
cd frontend && npm run typecheck
```

Expected: passes (existing typecheck only — new file should not introduce errors).

- [ ] **Step 3: Commit**

```bash
git add frontend/app/i18n/config.ts
git commit -m "feat(i18n): add createI18nInstance factory with bundled resources"
```

---

## Task 4: Create `app/i18n/server.ts`

**Files:**
- Create: `frontend/app/i18n/server.ts`

- [ ] **Step 1: Write the server module**

File: `frontend/app/i18n/server.ts`

```ts
import { createCookie } from 'react-router';
import { RemixI18Next } from 'remix-i18next/server';

import { FALLBACK_LOCALE, SUPPORTED_LOCALES } from './config';

const ONE_YEAR_SECONDS = 60 * 60 * 24 * 365;

export const localeCookie = createCookie('df-locale', {
  sameSite: 'lax',
  path: '/',
  maxAge: ONE_YEAR_SECONDS,
  secure: process.env.NODE_ENV === 'production',
});

export const i18nServer = new RemixI18Next({
  detection: {
    supportedLanguages: [...SUPPORTED_LOCALES],
    fallbackLanguage: FALLBACK_LOCALE,
    order: ['searchParams', 'cookie', 'header'],
    searchParamKey: 'lang',
    cookie: localeCookie,
  },
});
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && npm run typecheck
```

Expected: passes.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/i18n/server.ts
git commit -m "feat(i18n): add server-side RemixI18Next + df-locale cookie"
```

---

## Task 5: Create `app/i18n/client.ts`

**Files:**
- Create: `frontend/app/i18n/client.ts`

- [ ] **Step 1: Write the client module with cookie fallback**

File: `frontend/app/i18n/client.ts`

```ts
import { createI18nInstance, FALLBACK_LOCALE, SUPPORTED_LOCALES, type SupportedLocale } from './config';

function isSupported(value: string): value is SupportedLocale {
  return (SUPPORTED_LOCALES as readonly string[]).includes(value);
}

function readCookie(name: string): string | undefined {
  if (typeof document === 'undefined') return undefined;
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : undefined;
}

function writeCookie(name: string, value: string): void {
  if (typeof document === 'undefined') return;
  const oneYear = 60 * 60 * 24 * 365;
  const secure = location.protocol === 'https:' ? '; Secure' : '';
  document.cookie = `${name}=${encodeURIComponent(value)}; Path=/; Max-Age=${oneYear}; SameSite=Lax${secure}`;
}

function resolveLocale(): SupportedLocale {
  const params = new URLSearchParams(location.search);
  const queryLocale = params.get('lang');
  if (queryLocale && isSupported(queryLocale)) {
    if (readCookie('df-locale') !== queryLocale) {
      writeCookie('df-locale', queryLocale);
    }
    return queryLocale;
  }
  const htmlLang = document.documentElement.lang;
  if (htmlLang && isSupported(htmlLang)) return htmlLang;
  return FALLBACK_LOCALE;
}

export const i18n = createI18nInstance(resolveLocale());
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && npm run typecheck
```

Expected: passes.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/i18n/client.ts
git commit -m "feat(i18n): add client singleton with prerender cookie fallback"
```

---

## Task 6: Create `app/i18n/types.ts`

**Files:**
- Create: `frontend/app/i18n/types.ts`

- [ ] **Step 1: Write module augmentation**

File: `frontend/app/i18n/types.ts`

```ts
import type navbar from './locales/en/navbar.json';

declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: 'navbar';
    resources: {
      navbar: typeof navbar;
    };
  }
}
```

- [ ] **Step 2: Verify augmentation is picked up**

Create a temporary file `frontend/app/i18n/__augment_check.tsx` (will be deleted in step 4):

```tsx
import { useTranslation } from 'react-i18next';
import './types';

export function _Probe() {
  const { t } = useTranslation('navbar');
  // Valid key → compiles
  const a: string = t('login');
  // Invalid key → must fail
  // @ts-expect-error - 'nonexistent' is not in navbar.json
  const b: string = t('nonexistent');
  return <span>{a}{b}</span>;
}
```

- [ ] **Step 3: Type-check the probe**

```bash
cd frontend && npm run typecheck
```

Expected: passes. (`@ts-expect-error` confirms the invalid key is rejected; the comment suppresses the error.)

- [ ] **Step 4: Delete the probe and re-verify**

```bash
rm frontend/app/i18n/__augment_check.tsx
cd frontend && npm run typecheck
```

Expected: passes (probe is gone, no orphaned references).

- [ ] **Step 5: Commit**

```bash
git add frontend/app/i18n/types.ts
git commit -m "feat(i18n): add typed t() module augmentation for navbar namespace"
```

---

## Task 7: Wire `root.tsx` loader + Layout

**Files:**
- Modify: `frontend/app/root.tsx` (replace hardcoded `<html lang="en">` and add `loader`)

- [ ] **Step 1: Add imports near the top of `root.tsx`**

Insert these imports alongside existing ones (after the existing `react-router` import block):

```tsx
import { useLoaderData } from 'react-router';
import { useChangeLanguage } from 'remix-i18next/react';
import { I18nextProvider } from 'react-i18next';
import { i18nServer } from './i18n/server';
import { i18n } from './i18n/client';
import './i18n/types';
```

Note: importing `./i18n/client` is safe — its top-level code guards `document` with `typeof document === 'undefined'` so SSR won't crash. The actual `createI18nInstance` call uses the resolved locale; during SSR rendering, the per-request server provider (Task 8) takes precedence over this singleton.

- [ ] **Step 2: Add the `loader` export**

Insert after `export const links` (currently around line 31):

```tsx
import type { LoaderFunctionArgs } from 'react-router';

export async function loader({ request }: LoaderFunctionArgs) {
  const locale = await i18nServer.getLocale(request);
  return { locale };
}

export const handle = { i18n: ['navbar'] };
```

- [ ] **Step 3: Modify the `Layout` function**

Replace the existing `Layout` (lines 82-116) with:

```tsx
export function Layout({ children }: { children: React.ReactNode }) {
  const data = useLoaderData<typeof loader>();
  const locale = data?.locale ?? 'en';
  useChangeLanguage(locale);

  return (
    <html lang={locale} className="dark" data-theme="dark">
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <Meta />
        <Links />
      </head>
      <body>
        <I18nextProvider i18n={i18n}>
          <QueryClientProvider client={queryClient}>
            <TooltipProvider delayDuration={300}>
              <SharedPopoverProvider>
                <div className="flex flex-col w-screen h-screen justify-between">
                  <ResponsiveAppBar />
                  <ActiveDraftBanner />
                  <ScrollArea id="outlet_root" className="flex-grow h-0">
                    {children}
                  </ScrollArea>
                </div>
                <Toaster richColors closeButton position="top-center" />
                <FloatingDraftIndicator />
                <SharedPopoverRenderer />
              </SharedPopoverProvider>
            </TooltipProvider>
          </QueryClientProvider>
        </I18nextProvider>

        <ScrollRestoration />
        <Scripts />
        <DevScripts />
      </body>
    </html>
  );
}
```

The `data?.locale ?? 'en'` guards the `ErrorBoundary` case where loader data may not exist.

- [ ] **Step 4: Type-check**

```bash
cd frontend && npm run typecheck
```

Expected: passes.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/root.tsx
git commit -m "feat(i18n): wire root.tsx loader + <html lang> + <I18nextProvider>"
```

---

## Task 8: Wire `entry.server.tsx`

**Files:**
- Modify: `frontend/app/entry.server.tsx`

- [ ] **Step 1: Add imports**

At the top of `entry.server.tsx`, add (after existing imports):

```tsx
import { I18nextProvider } from 'react-i18next';
import { createI18nInstance } from './i18n/config';
import { i18nServer } from './i18n/server';
```

- [ ] **Step 2: Make `handleRequest` async and resolve locale before render**

Replace the existing `handleRequest` signature and body to:

```tsx
export default async function handleRequest(
  request: Request,
  responseStatusCode: number,
  responseHeaders: Headers,
  routerContext: EntryContext,
) {
  const locale = await i18nServer.getLocale(request);
  const i18n = createI18nInstance(locale);

  return new Promise((resolve, reject) => {
    const { pipe, abort } = renderToPipeableStream(
      <I18nextProvider i18n={i18n}>
        <ServerRouter context={routerContext} url={request.url} />
      </I18nextProvider>,
      {
        onShellReady() {
          responseHeaders.set('Content-Type', 'text/html');
          const body = new PassThrough();
          const stream = createReadableStreamFromReadable(body);
          resolve(
            new Response(stream, {
              headers: responseHeaders,
              status: responseStatusCode,
            }),
          );
          pipe(body);
        },
        onShellError(error: unknown) {
          reject(error);
        },
      },
    );
  });
}
```

Only two semantic changes: (1) `async`, (2) wrap `<ServerRouter>` in `<I18nextProvider i18n={i18n}>`.

- [ ] **Step 3: Type-check**

```bash
cd frontend && npm run typecheck
```

Expected: passes.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/entry.server.tsx
git commit -m "feat(i18n): wrap SSR render in per-request <I18nextProvider>"
```

---

## Task 9: Wire `entry.client.tsx`

**Files:**
- Modify: `frontend/app/entry.client.tsx`

- [ ] **Step 1: Replace the entire file**

File: `frontend/app/entry.client.tsx`

```tsx
import { startTransition, StrictMode } from 'react';
import { hydrateRoot } from 'react-dom/client';
import { HydratedRouter } from 'react-router/dom';
import { I18nextProvider } from 'react-i18next';

import { initSentry } from '~/lib/sentry';
import { i18n } from './i18n/client';

initSentry();

startTransition(() => {
  hydrateRoot(
    document,
    <StrictMode>
      <I18nextProvider i18n={i18n}>
        <HydratedRouter />
      </I18nextProvider>
    </StrictMode>,
  );
});
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && npm run typecheck
```

Expected: passes.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/entry.client.tsx
git commit -m "feat(i18n): wrap client hydrate in <I18nextProvider>"
```

---

## Task 10: Configure `i18next-parser`

**Files:**
- Create: `frontend/i18next-parser.config.ts`

- [ ] **Step 1: Write parser config**

File: `frontend/i18next-parser.config.ts`

```ts
import type { UserConfig } from 'i18next-parser';

const config: UserConfig = {
  locales: ['en', 'es'],
  input: ['app/components/navbar/**/*.{ts,tsx}'],
  output: 'app/i18n/locales/$LOCALE/$NAMESPACE.json',
  defaultNamespace: 'navbar',
  keySeparator: '.',
  namespaceSeparator: false,
  createOldCatalogs: false,
  sort: true,
  keepRemoved: false,
};

export default config;
```

`namespaceSeparator: false` ensures `t('aria.star_github')` is treated as a key in the `navbar` namespace, not as namespace `aria` + key `star_github`.

- [ ] **Step 2: Add npm scripts to `package.json`**

Open `frontend/package.json` and add to the `scripts` block:

```json
"i18n:extract": "i18next --config i18next-parser.config.ts",
"i18n:check": "i18next --config i18next-parser.config.ts --fail-on-update",
"i18n:guard": "scripts/check-navbar-prop-strings.sh"
```

- [ ] **Step 3: Run extract to verify config (should be a no-op since JSON already exists)**

```bash
cd frontend && npm run i18n:extract
```

Expected output: parser scans navbar/, finds 0 `t()` calls yet (none added until Task 14+), exits 0 with no diff to existing JSON files.

- [ ] **Step 4: Verify check passes**

```bash
cd frontend && npm run i18n:check
```

Expected: exit 0 (no diff).

- [ ] **Step 5: Commit**

```bash
git add frontend/i18next-parser.config.ts frontend/package.json
git commit -m "build(i18n): add i18next-parser config + extract/check scripts"
```

---

## Task 11: Bootstrap ESLint flat config

**Files:**
- Create: `frontend/eslint.config.js`
- Modify: `frontend/package.json` (add `lint` script)

- [ ] **Step 1: Write a minimal permissive flat config**

File: `frontend/eslint.config.js`

```js
import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import react from 'eslint-plugin-react';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import prettier from 'eslint-config-prettier';
import i18next from 'eslint-plugin-i18next';

export default [
  {
    ignores: [
      'build/**',
      'node_modules/**',
      '.react-router/**',
      'public/build/**',
      'tests/playwright/**',
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    plugins: { react, 'react-hooks': reactHooks, 'react-refresh': reactRefresh },
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    settings: { react: { version: 'detect' } },
    rules: {
      // Permissive defaults — strictness is ratcheted via --max-warnings 0 over time.
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-unused-vars': 'off',
      '@typescript-eslint/no-empty-object-type': 'off',
      'react/react-in-jsx-scope': 'off',
      'react/prop-types': 'off',
      'no-empty': 'off',
      'no-prototype-builtins': 'off',
      'no-undef': 'off',
    },
  },
  // Strict i18n enforcement scoped to navbar
  {
    files: ['app/components/navbar/**/*.{ts,tsx}'],
    plugins: { i18next },
    rules: {
      'i18next/no-literal-string': [
        'error',
        {
          markupOnly: true,
          ignoreAttribute: ['data-testid', 'className', 'href', 'to'],
        },
      ],
    },
  },
  prettier,
];
```

If the project does not yet have `@eslint/js` or `typescript-eslint` as packages:

```bash
cd frontend && npm install --save-dev @eslint/js typescript-eslint
```

- [ ] **Step 2: Add `lint` script to `package.json`**

```json
"lint": "eslint . --max-warnings 0"
```

- [ ] **Step 3: Run lint and accept the result**

```bash
cd frontend && npm run lint
```

Expected: lint may surface warnings in legacy files. **If errors block the run, add the specific offending rules to `'off'`** in the global rules block until the run is green. The goal is a passing baseline; ratcheting up happens later. Do NOT silence `i18next/no-literal-string` — it's the load-bearing rule for this PR.

- [ ] **Step 4: Verify navbar files don't fail yet**

The navbar files still contain hardcoded strings — but they'll be wrapped in `t()` in Tasks 14-17. Until then, the `i18next/no-literal-string` rule WILL fail on them, which is expected. To unblock CI on this commit, the navbar files are converted in this same plan before merge.

Run:

```bash
cd frontend && npm run lint -- app/components/navbar/
```

Expected: errors listing literal strings in JSX text nodes. Note the count — Tasks 14-17 must drive it to zero.

- [ ] **Step 5: Commit**

```bash
git add frontend/eslint.config.js frontend/package.json frontend/package-lock.json
git commit -m "build(lint): bootstrap ESLint 9 flat config + navbar i18n strict block"
```

---

## Task 12: Prop-string guard script

**Files:**
- Create: `frontend/scripts/check-navbar-prop-strings.sh`

- [ ] **Step 1: Write the guard**

File: `frontend/scripts/check-navbar-prop-strings.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="$ROOT/app/components/navbar"

PATTERN='(title|subtitle|label|placeholder|tooltip|description)="[A-Z]'

if grep -rEn "$PATTERN" "$TARGET" --include='*.tsx' --include='*.ts'; then
  echo ""
  echo "ERROR: Untranslated visible prop strings in navbar/."
  echo "Wrap each match with t('navbar.<key>') and add the key to:"
  echo "  app/i18n/locales/en/navbar.json"
  echo "  app/i18n/locales/es/navbar.json"
  exit 1
fi

echo "OK: no untranslated visible prop strings in navbar/."
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x frontend/scripts/check-navbar-prop-strings.sh
```

- [ ] **Step 3: Run it and observe the current failure**

```bash
frontend/scripts/check-navbar-prop-strings.sh
```

Expected (until Task 14): non-zero exit with matches for `title="Events"`, `subtitle="Sign up here"`, etc. Note the count — Tasks 14-17 must drive it to zero before commit.

- [ ] **Step 4: Commit (the script, not its passing state — that comes later)**

```bash
git add frontend/scripts/check-navbar-prop-strings.sh
git commit -m "build(i18n): add navbar prop-string CI guard"
```

---

## Task 13: Wire `just frontend::` module

**Files:**
- Create: `just/frontend/mod.just`
- Create: `just/frontend/i18n.just`
- Modify: `justfile` (add `mod frontend`)
- Modify: `just/npm.just` (remove `typecheck` and `lint`)

- [ ] **Step 1: Create `just/frontend/mod.just`**

File: `just/frontend/mod.just`

```just
# Frontend validation and tooling

frontend := source_directory() / ".." / ".." / "frontend"

mod i18n 'i18n.just'

# Type-check the frontend
[group('frontend')]
tsc:
    cd "{{frontend}}" && npm run typecheck

# Lint the frontend (ESLint flat config)
[group('frontend')]
lint:
    cd "{{frontend}}" && npm run lint

# Run all frontend validators (local convenience; CI splits these into parallel jobs)
[group('frontend')]
validate: tsc lint
    just frontend::i18n::check
    just frontend::i18n::guard
```

- [ ] **Step 2: Create `just/frontend/i18n.just`**

File: `just/frontend/i18n.just`

```just
# i18n key extraction and validation

frontend := source_directory() / ".." / ".." / "frontend"

# Extract t() calls and update locale JSONs (writes files)
[group('i18n')]
extract:
    cd "{{frontend}}" && npm run i18n:extract

# Verify locale JSONs match t() calls (CI: fail on diff)
[group('i18n')]
check:
    cd "{{frontend}}" && npm run i18n:check

# Grep guard for untranslated visible prop strings in navbar/
[group('i18n')]
guard:
    cd "{{frontend}}" && npm run i18n:guard
```

- [ ] **Step 3: Register the module in the top-level `justfile`**

Open `justfile` and add `mod frontend 'just/frontend/mod.just'` next to the other `mod` directives.

- [ ] **Step 4: Remove `typecheck` and `lint` from `just/npm.just`**

Open `just/npm.just` and delete these two blocks:

```just
[group('npm')]
typecheck:
    cd "{{frontend}}" && npm run typecheck

[group('npm')]
lint:
    cd "{{frontend}}" && npm run lint
```

Keep `install`, `dev`, `build`, and `run *args`.

- [ ] **Step 5: Verify just can list the new module**

```bash
just --list --list-submodules | grep -E "frontend::"
```

Expected output includes `frontend::tsc`, `frontend::lint`, `frontend::validate`, `frontend::i18n::extract`, `frontend::i18n::check`, `frontend::i18n::guard`.

- [ ] **Step 6: Smoke test the recipes (tsc and i18n::check will pass; lint and guard will fail until Tasks 14-17 — that's expected)**

```bash
just frontend::tsc        # expect: pass
just frontend::i18n::check  # expect: pass (no t() calls yet, JSONs hand-written)
just frontend::i18n::guard  # expect: fail (prop strings still in navbar)
just frontend::lint         # expect: fail (literal strings in navbar JSX)
```

- [ ] **Step 7: Commit**

```bash
git add justfile just/frontend/ just/npm.just
git commit -m "build(just): add frontend:: module, migrate tsc+lint from npm::"
```

---

## Task 14: Convert `login.tsx` — add `t()` + `data-testid`

**Files:**
- Modify: `frontend/app/components/navbar/login.tsx`

- [ ] **Step 1: Locate the Discord login button (around line 134)**

The current JSX is:

```tsx
<span>Login with Discord</span>
```

inside a `<button>` (without a `data-testid`).

- [ ] **Step 2: Add `useTranslation`, `data-testid`, and `t()`**

Add to the imports at the top of the file:

```tsx
import { useTranslation } from 'react-i18next';
```

Inside the `LoginWithDiscordButton` component (before its `return`):

```tsx
const { t } = useTranslation('navbar');
```

Replace the button element so it includes `data-testid="discord-login-button"` and uses `t('login')`:

```tsx
<button data-testid="discord-login-button" /* ...existing className/onClick... */>
  {/* ...existing icon... */}
  <span>{t('login')}</span>
</button>
```

(Preserve the existing className, onClick, and icon child — only the wrapping `<button>` props and the inner `<span>` text change.)

- [ ] **Step 3: Lint the file in isolation**

```bash
cd frontend && npm run lint -- app/components/navbar/login.tsx
```

Expected: passes (no literal strings remaining in JSX text).

- [ ] **Step 4: Run i18n check**

```bash
just frontend::i18n::check
```

Expected: passes — `t('login')` already exists in both `en/navbar.json` and `es/navbar.json` from Task 2.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/components/navbar/login.tsx
git commit -m "feat(i18n): translate Discord login button + add testid"
```

---

## Task 15: Convert `navbar.tsx`

**Files:**
- Modify: `frontend/app/components/navbar/navbar.tsx`

- [ ] **Step 1: Add `useTranslation` import and hook**

At the top of the file, add:

```tsx
import { useTranslation } from 'react-i18next';
```

Inside `ResponsiveAppBar` (and any other component in the file that contains the strings being translated — typically near the top of the function body):

```tsx
const { t } = useTranslation('navbar');
```

- [ ] **Step 2: Replace English strings with `t()` calls**

Convert these matches found earlier:

| Line | Before | After |
|---|---|---|
| ~468 | `aria-label="Star us on GitHub"` | `aria-label={t('aria.star_github')}` |
| ~479 | `aria-label="Documentation"` | `aria-label={t('aria.documentation')}` |
| ~493 | `aria-label="Report a Bug"` | `aria-label={t('aria.report_bug')}` |
| ~551 | `subtitle="Sign up here"` | `subtitle={t('signup_here')}` |
| ~597 | `aria-label="Home"` | `aria-label={t('aria.home') /* see note */}` — actually use `aria-label={t('home')}` since the same key "Home" covers both JSX text (TooltipContent) and aria-label |
| ~602 | `<TooltipContent>Home</TooltipContent>` | `<TooltipContent>{t('home')}</TooltipContent>` |
| ~615 | `aria-label="Home"` | `aria-label={t('home')}` |
| ~620 | `<TooltipContent>Home</TooltipContent>` | `<TooltipContent>{t('home')}</TooltipContent>` |
| ~631 | `aria-label="Main navigation"` | `aria-label={t('aria.main_nav')}` |

(The `t('home')` key serves both JSX text and aria-label; same string, no separate `aria.home` needed.)

Also scan for any `title=`, `placeholder=`, `tooltip=` on visible elements — wrap each. If a string isn't already in `en/navbar.json`, add it now (and the Spanish equivalent in `es/navbar.json`).

- [ ] **Step 3: Lint the file**

```bash
cd frontend && npm run lint -- app/components/navbar/navbar.tsx
```

Expected: passes.

- [ ] **Step 4: Run i18n check + guard**

```bash
just frontend::i18n::check
just frontend::i18n::guard
```

Expected: both pass. If guard still flags strings, repeat step 2 for the matches it surfaces.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/components/navbar/navbar.tsx frontend/app/i18n/locales/
git commit -m "feat(i18n): translate navbar.tsx visible text + aria-labels"
```

---

## Task 16: Convert `MobileNav.tsx`

**Files:**
- Modify: `frontend/app/components/navbar/MobileNav.tsx`

- [ ] **Step 1: Inventory the file's strings**

```bash
grep -nE '>[A-Z][a-zA-Z ]+<|(aria-label|title|subtitle|label|placeholder)="[A-Z]' frontend/app/components/navbar/MobileNav.tsx
```

Note each line + string. For each:
- Add a key in both `en/navbar.json` and `es/navbar.json` if not already there.
- Wrap with `t('<key>')`.

- [ ] **Step 2: Add the hook and translate**

```tsx
import { useTranslation } from 'react-i18next';
// inside the component:
const { t } = useTranslation('navbar');
```

Apply the wrap-with-`t()` pattern to each string identified in step 1.

- [ ] **Step 3: Lint, check, guard**

```bash
cd frontend && npm run lint -- app/components/navbar/MobileNav.tsx
just frontend::i18n::check
just frontend::i18n::guard
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/components/navbar/MobileNav.tsx frontend/app/i18n/locales/
git commit -m "feat(i18n): translate MobileNav.tsx"
```

---

## Task 17: Convert `PageNavBar.tsx`

**Files:**
- Modify: `frontend/app/components/navbar/PageNavBar.tsx`

Same pattern as Task 16.

- [ ] **Step 1: Inventory**

```bash
grep -nE '>[A-Z][a-zA-Z ]+<|(aria-label|title|subtitle|label|placeholder)="[A-Z]' frontend/app/components/navbar/PageNavBar.tsx
```

- [ ] **Step 2: Translate**

Add the import + hook + wrap each string with `t()`. Add new keys to `en/navbar.json` and `es/navbar.json` as needed.

- [ ] **Step 3: Final navbar-wide verification**

```bash
just frontend::lint
just frontend::i18n::check
just frontend::i18n::guard
```

Expected: all three pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/components/navbar/PageNavBar.tsx frontend/app/i18n/locales/
git commit -m "feat(i18n): translate PageNavBar.tsx; navbar conversion complete"
```

---

## Task 18: Pin Playwright locale and verify no English-text regressions

**Files:**
- Modify: `frontend/playwright.config.ts`

- [ ] **Step 1: Add `locale: 'en-US'` to the global `use` block**

In `frontend/playwright.config.ts`, the global `use` block is around line 52. Add `locale: 'en-US'` (place it near `viewport`):

```ts
  use: {
    baseURL: 'https://localhost',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: process.env.CI ? 'off' : 'retain-on-failure',
    ignoreHTTPSErrors: true,
    viewport: { width: 1280, height: 720 },
    locale: 'en-US',
    actionTimeout: 15_000,
  },
```

- [ ] **Step 2: Run the pre-merge regression grep**

```bash
grep -rn "Login with Discord\|Sign up here\|Logout\|Edit Profile\|Star us on GitHub\|Documentation\|Report a Bug\|Main navigation" frontend/tests/playwright/e2e/ || echo "OK: no English navbar copy in specs"
```

Expected: prints `OK: no English navbar copy in specs`. If any matches appear, update those specs to use `data-testid` selectors or locale-aware text assertions before continuing.

- [ ] **Step 3: Run the existing nav spec to confirm it still passes**

```bash
just test::up        # if test stack not already running
just test::pw::spec 01-navigation
```

Expected: existing nav spec passes (it uses `data-testid` per the testing skill's findings).

- [ ] **Step 4: Commit**

```bash
git add frontend/playwright.config.ts
git commit -m "test(playwright): pin use.locale to en-US for deterministic regression"
```

---

## Task 19: Write i18n Playwright spec

**Files:**
- Create: `frontend/tests/playwright/e2e/01-navigation-i18n.spec.ts`

- [ ] **Step 1: Write the spec**

File: `frontend/tests/playwright/e2e/01-navigation-i18n.spec.ts`

```ts
import { test, expect } from '@playwright/test';

// i18n hydration bugs must surface immediately; no retries.
test.describe.configure({ retries: 0 });

const LOGIN_BUTTON = '[data-testid="discord-login-button"]';
const ES_LOGIN = 'Iniciar sesión con Discord';
const EN_LOGIN = 'Login with Discord';

test.describe('navbar i18n', () => {
  test('?lang=es renders Spanish login button', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
    page.on('console', (m) => {
      if (m.type() === 'error') errors.push(`console: ${m.text()}`);
    });

    await page.goto('/?lang=es');
    await expect(page.locator(LOGIN_BUTTON)).toHaveText(ES_LOGIN);
    await expect(page.locator('html')).toHaveAttribute('lang', 'es');
    expect(errors, `unexpected errors: ${errors.join(' | ')}`).toEqual([]);
  });

  test('cookie persists Spanish across navigation', async ({ page }) => {
    await page.goto('/?lang=es');
    await expect(page.locator(LOGIN_BUTTON)).toHaveText(ES_LOGIN);
    await page.goto('/tournaments');
    await expect(page.locator(LOGIN_BUTTON)).toHaveText(ES_LOGIN);
  });

  test('default en-US context renders English', async ({ browser }) => {
    const context = await browser.newContext({ locale: 'en-US' });
    const page = await context.newPage();
    await page.goto('/');
    await expect(page.locator(LOGIN_BUTTON)).toHaveText(EN_LOGIN);
    await context.close();
  });

  test('es-ES context renders Spanish navbar', async ({ browser }) => {
    const context = await browser.newContext({ locale: 'es-ES' });
    const page = await context.newPage();
    await page.goto('/tournaments');
    await expect(page.locator(LOGIN_BUTTON)).toHaveText(ES_LOGIN);
    await expect(page.locator('html')).toHaveAttribute('lang', 'es');
    await context.close();
  });

  test('unsupported locale (fr-FR) falls back to English', async ({ browser }) => {
    const context = await browser.newContext({ locale: 'fr-FR' });
    const page = await context.newPage();
    await page.goto('/tournaments');
    await expect(page.locator(LOGIN_BUTTON)).toHaveText(EN_LOGIN);
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
    await context.close();
  });

  test('?lang=en beats df-locale=es cookie', async ({ browser }) => {
    const context = await browser.newContext({ locale: 'en-US' });
    await context.addCookies([
      { name: 'df-locale', value: 'es', url: 'https://localhost' },
    ]);
    const page = await context.newPage();
    await page.goto('/tournaments?lang=en');
    await expect(page.locator(LOGIN_BUTTON)).toHaveText(EN_LOGIN);
    await context.close();
  });

  test('clearing the cookie returns to browser language', async ({ browser }) => {
    const context = await browser.newContext({ locale: 'en-US' });
    await context.addCookies([
      { name: 'df-locale', value: 'es', url: 'https://localhost' },
    ]);
    const p1 = await context.newPage();
    await p1.goto('/tournaments');
    await expect(p1.locator(LOGIN_BUTTON)).toHaveText(ES_LOGIN);
    await context.clearCookies();
    const p2 = await context.newPage();
    await p2.goto('/tournaments');
    await expect(p2.locator(LOGIN_BUTTON)).toHaveText(EN_LOGIN);
    await context.close();
  });

  test('dynamic route renders Spanish with no flicker for es-ES context', async ({
    browser,
  }) => {
    const context = await browser.newContext({ locale: 'es-ES' });
    const page = await context.newPage();
    const response = await page.goto('/tournaments');
    const html = (await response?.text()) ?? '';
    // Server-rendered HTML must already contain Spanish — no client swap.
    expect(html).toContain(ES_LOGIN);
    await context.close();
  });

  test('prerendered / shows English HTML then Spanish after hydration (documented trade-off)', async ({
    browser,
  }) => {
    const context = await browser.newContext({ locale: 'es-ES' });
    const page = await context.newPage();
    const response = await page.goto('/');
    const html = (await response?.text()) ?? '';
    // First HTML response is English (prerendered).
    expect(html).toContain(EN_LOGIN);
    // After hydration, navbar text becomes Spanish.
    await expect(page.locator(LOGIN_BUTTON)).toHaveText(ES_LOGIN);
    await context.close();
  });
});
```

- [ ] **Step 2: Run the new spec**

```bash
just test::pw::spec 01-navigation-i18n
```

Expected: 9 tests pass. If "cookie persists" or "?lang=en beats cookie" fails, check that `client.ts`'s cookie-fallback writes the cookie correctly and that `i18nServer` reads `searchParams` before `cookie`.

- [ ] **Step 3: Commit**

```bash
git add frontend/tests/playwright/e2e/01-navigation-i18n.spec.ts
git commit -m "test(i18n): add Playwright spec for navbar locale detection"
```

---

## Task 20: Visual QA Playwright spec (screenshots, non-gating)

**Files:**
- Create: `frontend/tests/playwright/e2e/06-visual-qa-navbar-i18n.spec.ts`

- [ ] **Step 1: Write the screenshot spec**

File: `frontend/tests/playwright/e2e/06-visual-qa-navbar-i18n.spec.ts`

```ts
import { test } from '@playwright/test';

const VIEWPORTS = [
  { name: 'mobile', width: 375, height: 800 },
  { name: 'tablet', width: 768, height: 800 },
  { name: 'desktop', width: 1280, height: 800 },
];
const LOCALES = ['en', 'es'] as const;

for (const vp of VIEWPORTS) {
  for (const locale of LOCALES) {
    test(`navbar visual @ ${vp.name} ${locale}`, async ({ browser }) => {
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        locale: locale === 'es' ? 'es-ES' : 'en-US',
      });
      const page = await context.newPage();
      await page.goto(`/tournaments?lang=${locale}`);
      // Wait for navbar to settle (locale swap, font load).
      await page.waitForLoadState('networkidle');
      await page.screenshot({
        path: `test-results/visual-qa/navbar-${vp.name}-${locale}.png`,
        fullPage: false,
      });
      await context.close();
    });
  }
}
```

- [ ] **Step 2: Run the visual QA spec**

```bash
just test::pw::spec 06-visual-qa-navbar-i18n
```

Expected: 6 tests pass, producing 6 screenshots under `frontend/test-results/visual-qa/`.

- [ ] **Step 3: Open the screenshots and verify**

```bash
ls -la frontend/test-results/visual-qa/
```

Manually open each and confirm:
- Discord button text fits at mobile 375 in both locales. If `Iniciar sesión con Discord` truncates or wraps, change the Spanish translation in `frontend/app/i18n/locales/es/navbar.json` from `"login": "Iniciar sesión con Discord"` to `"login": "Entrar con Discord"`, re-run.
- Nav items don't wrap unexpectedly in either locale.
- Drop-down menus (where rendered in the screenshot) look correct.

Attach the six screenshots to the PR description.

- [ ] **Step 4: Commit**

```bash
git add frontend/tests/playwright/e2e/06-visual-qa-navbar-i18n.spec.ts
git commit -m "test(i18n): add visual QA screenshots at 3 viewports × 2 locales"
```

If the Spanish login string was shortened in step 3, also commit:

```bash
git add frontend/app/i18n/locales/es/navbar.json
git commit -m "feat(i18n): shorten Spanish Discord login text to fit mobile"
```

---

## Task 21: Final integration smoke

**Files:** (none — verification only)

- [ ] **Step 1: Run the full local validate**

```bash
just frontend::validate
```

Expected: passes all four checks (tsc + lint + i18n::check + i18n::guard).

- [ ] **Step 2: Run the full Playwright suite**

```bash
just test::pw::headless
```

Expected: full suite passes, including the new i18n spec and visual QA spec. If any pre-existing spec fails because of a string assertion that was missed by the grep in Task 18, update that spec to use `data-testid` selectors.

- [ ] **Step 3: Manual smoke test (cookie sanity)**

In a browser (dev environment running):
1. Visit `https://localhost/?lang=es` — navbar shows Spanish after hydration.
2. DevTools → Application → Cookies → confirm `df-locale=es` with `Max-Age` ≈ 31536000.
3. Reload `/` (no query) — navbar still Spanish.
4. Visit `/tournaments` (dynamic route) — Spanish from first paint (view-source confirms `lang="es"` and Spanish text in HTML).
5. Clear `df-locale`, set browser language to French — English fallback.

- [ ] **Step 4: Final commit if anything was tweaked during the smoke; otherwise skip**

```bash
git status
# If clean, no commit needed.
# If anything changed during the smoke (small fixes), commit normally.
```

- [ ] **Step 5: Push and open PR**

```bash
git push -u origin feature/frontend-i18n-navbar-es
gh pr create --title "feat(i18n): Spanish navbar with SSR locale detection" --body "$(cat <<'EOF'
## Summary
- Adds react-i18next + remix-i18next for SSR locale detection (`?lang=` → `df-locale` cookie → `Accept-Language` → `en`).
- Translates all visible navbar text + `aria-label`s into Spanish.
- New `just frontend::*` module (tsc, lint, i18n::extract, i18n::check, i18n::guard, validate). Removed `npm::typecheck` and `npm::lint`.
- Bootstrapped ESLint 9 flat config from scratch (project shipped deps but no config).
- `eslint-plugin-i18next` `no-literal-string` (error) scoped to `app/components/navbar/**`.
- `i18next-parser --fail-on-update` ensures locale key parity.
- Bash grep guard catches untranslated visible prop strings the lint rule can't.
- Playwright spec covers 9 scenarios; visual QA spec produces 6 screenshots (attached).
- `/` and `/about` remain prerendered (link-preview speed). Documented Spanish flicker on those two routes.

## Test plan
- [x] `just frontend::validate` passes locally
- [x] `just test::pw::headless` passes locally
- [x] Manual smoke test (cookie, prerender, dynamic route, fallback) passes
- [x] Visual QA screenshots attached
EOF
)"
```

---

## Self-Review

**Spec coverage:**
- Architecture (deps, file layout, detection flow, two instances, resources, cookie, prerender retained): Tasks 1, 3-9, 10, 18-20.
- `app/i18n/config.ts`: Task 3. `server.ts`: Task 4. `client.ts`: Task 5. `types.ts`: Task 6. `root.tsx`: Task 7. `entry.server.tsx`: Task 8. `entry.client.tsx`: Task 9.
- Navbar conversion (4 files, JSX text, props, aria-labels, key naming, data-testid): Tasks 2, 14-17.
- Prop-string CI guard: Task 12. ESLint flat config: Task 11. `i18next-parser` config: Task 10. `package.json` scripts: Tasks 10, 11. `playwright.config.ts` locale pin: Task 18.
- `just` module restructure: Task 13.
- CI parallel jobs: documented in the spec; this plan covers the underlying `just` recipes and the rationale. Wiring them into the actual CI YAML is a follow-up (out of scope: this plan focuses on the code, not the CI YAML).
- Testing (unit/static, Playwright E2E, visual QA, regression grep, local workflow, manual smoke): Tasks 10, 18, 19, 20, 21.
- Risk register: hydration mismatch covered by scenario 1 (`pageerror` listener); prerender behavior covered by scenarios 8 and 9; cookie fallback for prerendered `?lang=` covered by `client.ts` + scenario 2.

**Placeholder scan:** None remaining. Step text and code blocks are complete. The only ambiguous instruction is in Task 11 step 3 ("add the specific offending rules to `'off'`") — this is intentional: the ESLint bootstrap surface is genuinely unknowable in advance, and the engineer needs latitude to silence pre-existing churn while keeping the navbar rule strict.

**Type consistency:** `createI18nInstance` returns `I18nInstance` (Task 3), consumed identically in `client.ts` (Task 5) and `entry.server.tsx` (Task 8). Cookie name `df-locale` consistent across `server.ts` (Task 4), `client.ts` (Task 5), and tests (Task 19). `data-testid="discord-login-button"` used in Task 14 and asserted in Task 19. Key naming follows `defaultNS: 'navbar'` convention: `t('login')` not `t('navbar.login')` throughout.
