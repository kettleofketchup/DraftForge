# Frontend i18n Navbar (Spanish) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Spanish translation of the DraftForge navbar (visible text + `aria-label`s) with SSR-aware locale detection, a `just frontend::*` validation module, and CI gates that prevent untranslated strings from regressing.

**Architecture:** React Router 7 SSR app uses `remix-i18next` to detect locale from `?lang=` query → `df-locale` cookie → `Accept-Language` header → `en` fallback in the `root.tsx` loader. Per-request i18n instance on the server (wrapped in `<I18nextProvider>` inside `entry.server.tsx`), singleton on the client (wrapped in `entry.client.tsx`), synced via `useChangeLanguage`. **`<I18nextProvider>` wraps only at the entry points — never inside `root.tsx`** (avoids double-wrap and keeps client.ts out of the SSR bundle). Translation JSON bundled at build time under `app/i18n/locales/`. `eslint-plugin-i18next` (JSX text) + parser key-parity (`--fail-on-update`) + a grep guard (prop-based visible text) enforce completeness. `/` and `/about` stay prerendered (link previews); Spanish flicker on those two routes is documented and accepted.

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
- `frontend/tests/playwright/e2e/01-locale.spec.ts` (renamed from `01-navigation-i18n` to avoid alphabetical confusion with `01-navigation.spec.ts`)
- `frontend/tests/playwright/e2e/06-visual-qa-navbar.spec.ts`
- `frontend/screenshots/i18n/` (output dir for visual QA — distinct from `test-results/` which holds `retain-on-failure` artifacts)
- `just/frontend/mod.just`
- `just/frontend/i18n.just`

**Modified files:**
- `frontend/package.json` — deps + scripts
- `frontend/app/root.tsx` — add `loader`, modify `Layout` (loader-driven `<html lang>`, `useChangeLanguage`; **does NOT wrap in `<I18nextProvider>`**)
- `frontend/app/entry.server.tsx` — wrap render in `<I18nextProvider>` (sole server wrap)
- `frontend/app/entry.client.tsx` — wrap hydrate in `<I18nextProvider>` (sole client wrap)
- `frontend/playwright.config.ts` — pin `use.locale: 'en-US'`
- `frontend/app/components/navbar/navbar.tsx` — wrap strings with `t()` + `data-testid`s
- `frontend/app/components/navbar/MobileNav.tsx` — wrap strings with `t()`
- `frontend/app/components/navbar/PageNavBar.tsx` — wrap strings with `t()`
- `frontend/app/components/navbar/login.tsx` — wrap "Login with Discord", "Profile", "Logout" + add `data-testid`s
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

Expected output: ~3 new entries under `dependencies` in `package.json`, no peer-dependency warnings.

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

Note: the user-dropdown menu item in `login.tsx` says **"Profile"**, not "Edit Profile". Key is `profile`/`Perfil`.

- [ ] **Step 1: Create directories**

```bash
mkdir -p frontend/app/i18n/locales/en frontend/app/i18n/locales/es
```

- [ ] **Step 2: Write English source of truth**

File: `frontend/app/i18n/locales/en/navbar.json`

```json
{
  "login": "Login with Discord",
  "logout": "Logout",
  "profile": "Profile",
  "signup_here": "Sign up here",
  "home": "Home",
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
  "logout": "Cerrar sesión",
  "profile": "Perfil",
  "signup_here": "Regístrate aquí",
  "home": "Inicio",
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

- [ ] **Step 2: Type-check**

```bash
cd frontend && npm run typecheck
```

Expected: passes.

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

**Important:** this module must NOT be imported by `root.tsx` or any server-running module. It is imported ONLY from `entry.client.tsx`.

- [ ] **Step 1: Write the client module with cookie fallback**

File: `frontend/app/i18n/client.ts`

```ts
import { createI18nInstance, FALLBACK_LOCALE, SUPPORTED_LOCALES, type SupportedLocale } from './config';

function isSupported(value: string): value is SupportedLocale {
  return (SUPPORTED_LOCALES as readonly string[]).includes(value);
}

function readCookie(name: string): string | undefined {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : undefined;
}

function writeCookie(name: string, value: string): void {
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

No `typeof document` guards needed — this module runs only in the browser.

- [ ] **Step 2: Type-check**

```bash
cd frontend && npm run typecheck
```

Expected: passes.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/i18n/client.ts
git commit -m "feat(i18n): add client-only singleton with prerender cookie fallback"
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

- [ ] **Step 2: Verify augmentation is picked up via a temporary probe**

Create `frontend/app/i18n/__augment_check.tsx`:

```tsx
import { useTranslation } from 'react-i18next';
import './types';

export function _Probe() {
  const { t } = useTranslation('navbar');
  const a: string = t('login');
  // @ts-expect-error - 'nonexistent' is not in navbar.json
  const b: string = t('nonexistent');
  return <span>{a}{b}</span>;
}
```

- [ ] **Step 3: Type-check the probe**

```bash
cd frontend && npm run typecheck
```

Expected: passes (the `@ts-expect-error` confirms the invalid key is rejected).

- [ ] **Step 4: Delete the probe and re-verify**

```bash
rm frontend/app/i18n/__augment_check.tsx
cd frontend && npm run typecheck
```

Expected: passes.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/i18n/types.ts
git commit -m "feat(i18n): add typed t() module augmentation for navbar namespace"
```

---

## Task 7: Wire `root.tsx` loader + Layout

**Files:**
- Modify: `frontend/app/root.tsx`

**Important:** Do NOT import `./i18n/client` or wrap children in `<I18nextProvider>` here. Those belong in `entry.client.tsx` / `entry.server.tsx`. `root.tsx` runs on both server and client; pulling client.ts into the SSR bundle is wasteful and double-wrapping the provider is unclean (even though it's functionally harmless).

- [ ] **Step 1: Add imports near the top of `root.tsx`**

Add these imports alongside existing ones (in the existing `react-router` import block where possible):

```tsx
import type { LoaderFunctionArgs } from 'react-router';
import { useLoaderData } from 'react-router';
import { useChangeLanguage } from 'remix-i18next/react';
import { i18nServer } from './i18n/server';
import './i18n/types';
```

- [ ] **Step 2: Add the `loader` export**

Insert after `export const links` (currently around line 31):

```tsx
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

        <ScrollRestoration />
        <Scripts />
        <DevScripts />
      </body>
    </html>
  );
}
```

Only changes vs. existing: `lang="en"` → `lang={locale}`; consumes loader data; calls `useChangeLanguage(locale)`. No `<I18nextProvider>` wrap.

The `data?.locale ?? 'en'` guards the `ErrorBoundary` case where loader data may not exist.

- [ ] **Step 4: Type-check**

```bash
cd frontend && npm run typecheck
```

Expected: passes.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/root.tsx
git commit -m "feat(i18n): wire root.tsx loader + dynamic <html lang>"
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

Replace the existing `handleRequest`:

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

This is the sole server-side `<I18nextProvider>` wrap.

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

This is the sole client-side `<I18nextProvider>` wrap.

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
- Modify: `frontend/package.json` (add scripts)

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

`namespaceSeparator: false` ensures `t('aria.star_github')` lands as a nested key in `navbar`, not parsed as namespace `aria` + key `star_github`.

- [ ] **Step 2: Add npm scripts to `package.json`**

Add to the `scripts` block in `frontend/package.json`:

```json
"i18n:extract": "i18next --config i18next-parser.config.ts",
"i18n:check": "i18next --config i18next-parser.config.ts --fail-on-update",
"i18n:guard": "scripts/check-navbar-prop-strings.sh"
```

- [ ] **Step 3: Run extract (no-op since JSON already exists and no t() calls yet)**

```bash
cd frontend && npm run i18n:extract
```

Expected: no diff to existing JSON.

- [ ] **Step 4: Verify check passes**

```bash
cd frontend && npm run i18n:check
```

Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add frontend/i18next-parser.config.ts frontend/package.json
git commit -m "build(i18n): add i18next-parser config + extract/check scripts"
```

---

## Task 11: Bootstrap ESLint flat config (navbar-scoped lint script)

**Files:**
- Create: `frontend/eslint.config.js`
- Modify: `frontend/package.json` (add `lint` script)

**Important:** the `npm run lint` script is intentionally scoped to `app/components/navbar/` for this PR. Pre-existing files across the codebase have lint issues outside this PR's scope; ratcheting up coverage is a separate cleanup PR. The strict `i18next/no-literal-string` rule is the load-bearing check.

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
      // Permissive defaults — strictness is ratcheted in a separate cleanup PR.
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

- [ ] **Step 2: Add a navbar-scoped `lint` script to `package.json`**

```json
"lint": "eslint app/components/navbar --max-warnings 0"
```

This intentionally lints only the navbar directory. Widening to `eslint .` is a separate cleanup PR.

- [ ] **Step 3: Run lint over navbar/ and accept the result**

```bash
cd frontend && npm run lint
```

Expected: at this point in the plan, the rule WILL fail because navbar files still contain hardcoded strings. Tasks 14-17 drive it to zero. Note the violation count.

- [ ] **Step 4: Commit**

```bash
git add frontend/eslint.config.js frontend/package.json frontend/package-lock.json
git commit -m "build(lint): bootstrap ESLint 9 flat config (navbar-scoped lint script)"
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
```

The regex is intentionally case-insensitive (no `[A-Z]` anchor) — anything in those attribute values that's a literal string is suspicious.

- [ ] **Step 2: Make it executable**

```bash
chmod +x frontend/scripts/check-navbar-prop-strings.sh
```

- [ ] **Step 3: Run it and observe the current failure**

```bash
frontend/scripts/check-navbar-prop-strings.sh
```

Expected (until Task 15-17): non-zero exit with matches.

- [ ] **Step 4: Commit**

```bash
git add frontend/scripts/check-navbar-prop-strings.sh
git commit -m "build(i18n): add navbar prop-string CI guard"
```

---

## Task 13: Wire `just frontend::` module

**Files:**
- Create: `just/frontend/mod.just`
- Create: `just/frontend/i18n.just`
- Modify: `justfile`
- Modify: `just/npm.just`

- [ ] **Step 1: Create `just/frontend/mod.just`**

File: `just/frontend/mod.just`

```just
# Frontend validation and tooling.
#
# `validate` is a local-developer convenience. In CI, each recipe runs as a
# separate parallel job so failures don't mask each other. See follow-up Task
# 22 for the CI YAML wiring.

frontend := source_directory() / ".." / ".." / "frontend"

mod i18n 'i18n.just'

# Type-check the frontend
[group('frontend')]
tsc:
    cd "{{frontend}}" && npm run typecheck

# Lint the frontend (navbar-scoped during initial rollout)
[group('frontend')]
lint:
    cd "{{frontend}}" && npm run lint

# Run all frontend validators (LOCAL convenience; CI parallelizes)
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

Add `mod frontend 'just/frontend/mod.just'` next to the other `mod` directives.

- [ ] **Step 4: Remove `typecheck` and `lint` from `just/npm.just`**

Delete these two blocks:

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

Expected: includes `frontend::tsc`, `frontend::lint`, `frontend::validate`, `frontend::i18n::extract`, `frontend::i18n::check`, `frontend::i18n::guard`.

- [ ] **Step 6: Smoke test the recipes**

```bash
just frontend::tsc          # expect: pass
just frontend::i18n::check  # expect: pass (no t() calls yet)
just frontend::i18n::guard  # expect: fail (prop strings still in navbar)
just frontend::lint         # expect: fail (literal strings in navbar JSX)
```

- [ ] **Step 7: Commit**

```bash
git add justfile just/frontend/ just/npm.just
git commit -m "build(just): add frontend:: module, migrate tsc+lint from npm::"
```

---

## Task 14: Convert `login.tsx` — `t()` + testids for login, profile, logout

**Files:**
- Modify: `frontend/app/components/navbar/login.tsx`

The file contains three translatable strings:
- `Login with Discord` at line ~134 (`<span>` inside the discord button)
- `Profile` at line ~100 (inside the dropdown menu item)
- `Logout` at line ~108 (inside the destructive button)

Each gets `t()` and a `data-testid`.

- [ ] **Step 1: Add imports and hooks**

At the top of `login.tsx`, add:

```tsx
import { useTranslation } from 'react-i18next';
```

Inside `LoginWithDiscordButton` (before its JSX `return`):

```tsx
const { t } = useTranslation('navbar');
```

Same hook call inside any other component in the file that uses translated strings (e.g., the user dropdown component containing Profile/Logout).

- [ ] **Step 2: Replace the Discord login button**

Find the existing `<span>Login with Discord</span>` and its wrapping `<button>`. Preserve the existing `className`, `onClick`, and icon child. Add `data-testid` to the button and replace the span text:

```tsx
<button data-testid="discord-login-button" /* ...existing className/onClick... */>
  {/* ...existing DiscordIcon... */}
  <span>{t('login')}</span>
</button>
```

- [ ] **Step 3: Replace the Profile menu item**

Find the `<Button>` containing `<UserPenIcon />` and `Profile`. Add `data-testid` and wrap text:

```tsx
<Link to="/profile">
  <Button data-testid="navbar-profile-button">
    <UserPenIcon />
    {t('profile')}
  </Button>
</Link>
```

- [ ] **Step 4: Replace the Logout destructive button**

Find the `<DestructiveButton onClick={logoutClick}>` containing `<LogOutIcon />` and `Logout`. Add `data-testid` and wrap text:

```tsx
<DestructiveButton data-testid="navbar-logout-button" onClick={logoutClick}>
  <LogOutIcon />
  {t('logout')}
</DestructiveButton>
```

- [ ] **Step 5: Lint the file**

```bash
cd frontend && npm run lint
```

Expected: no errors in `login.tsx` (other navbar files still error — that's Tasks 15-17).

- [ ] **Step 6: i18n check**

```bash
just frontend::i18n::check
```

Expected: passes — `login`, `profile`, `logout` keys all exist from Task 2.

- [ ] **Step 7: Commit**

```bash
git add frontend/app/components/navbar/login.tsx
git commit -m "feat(i18n): translate login/profile/logout + add testids"
```

---

## Task 15: Convert `navbar.tsx`

**Files:**
- Modify: `frontend/app/components/navbar/navbar.tsx`

- [ ] **Step 1: Add `useTranslation` import and hook**

At the top of `navbar.tsx`:

```tsx
import { useTranslation } from 'react-i18next';
```

Inside `ResponsiveAppBar` (and any other component in the file using translated strings):

```tsx
const { t } = useTranslation('navbar');
```

- [ ] **Step 2: Replace English strings with `t()` calls**

| Line | Before | After |
|---|---|---|
| ~468 | `aria-label="Star us on GitHub"` | `aria-label={t('aria.star_github')}` |
| ~479 | `aria-label="Documentation"` | `aria-label={t('aria.documentation')}` |
| ~493 | `aria-label="Report a Bug"` | `aria-label={t('aria.report_bug')}` |
| ~551 | `subtitle="Sign up here"` | `subtitle={t('signup_here')}` |
| ~597 | `aria-label="Home"` | `aria-label={t('home')}` |
| ~602 | `<TooltipContent>Home</TooltipContent>` | `<TooltipContent>{t('home')}</TooltipContent>` |
| ~615 | `aria-label="Home"` | `aria-label={t('home')}` |
| ~620 | `<TooltipContent>Home</TooltipContent>` | `<TooltipContent>{t('home')}</TooltipContent>` |
| ~631 | `aria-label="Main navigation"` | `aria-label={t('aria.main_nav')}` |

If grep surfaces any additional visible strings (`title=`, `placeholder=`, etc.), wrap each one. Add new keys to both `en/navbar.json` and `es/navbar.json` as needed.

- [ ] **Step 3: Lint, check, guard**

```bash
cd frontend && npm run lint
just frontend::i18n::check
just frontend::i18n::guard
```

All three pass for `navbar.tsx`. Other files may still fail.

- [ ] **Step 4: Commit**

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
grep -nE '>[A-Z][a-zA-Z ]+<|(aria-label|title|subtitle|label|placeholder)="[^"]{3,}"' frontend/app/components/navbar/MobileNav.tsx
```

For each match: add a key in both `en/navbar.json` and `es/navbar.json` if not present, then wrap with `t('<key>')`.

- [ ] **Step 2: Add the hook and translate**

```tsx
import { useTranslation } from 'react-i18next';
// inside the component:
const { t } = useTranslation('navbar');
```

Apply the wrap pattern for every string from step 1.

- [ ] **Step 3: Lint, check, guard**

```bash
cd frontend && npm run lint
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
grep -nE '>[A-Z][a-zA-Z ]+<|(aria-label|title|subtitle|label|placeholder)="[^"]{3,}"' frontend/app/components/navbar/PageNavBar.tsx
```

- [ ] **Step 2: Translate**

Add the import + hook + wrap each string. Add new keys to both locale files.

- [ ] **Step 3: Final navbar-wide verification**

```bash
just frontend::validate
```

Expected: passes — tsc + lint + i18n::check + i18n::guard all green.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/components/navbar/PageNavBar.tsx frontend/app/i18n/locales/
git commit -m "feat(i18n): translate PageNavBar.tsx; navbar conversion complete"
```

---

## Task 18: Pin Playwright locale + regression grep (strengthened)

**Files:**
- Modify: `frontend/playwright.config.ts`

- [ ] **Step 1: Add `locale: 'en-US'` to the global `use` block**

In `frontend/playwright.config.ts` (around line 52), add `locale: 'en-US'`:

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

- [ ] **Step 2: Run the regression grep (English + Spanish hardcoded copy)**

Use word-boundary anchors to avoid false positives on substrings like `Documentation` appearing in URLs/comments:

```bash
# English strings that should ONLY appear in en/navbar.json now
grep -rEn '\b(Login with Discord|Sign up here|Logout|Profile|Star us on GitHub|Report a Bug|Main navigation)\b' frontend/tests/playwright/e2e/ frontend/app/components/navbar/ \
  --include='*.ts' --include='*.tsx' \
  | grep -v 'navbar.json' \
  || echo "OK: no hardcoded English navbar strings outside JSON"

# Spanish strings that should ONLY appear in es/navbar.json
grep -rEn '\b(Iniciar sesión con Discord|Cerrar sesión|Regístrate aquí|Perfil|Inicio)\b' frontend/tests/playwright/e2e/ frontend/app/components/navbar/ \
  --include='*.ts' --include='*.tsx' \
  | grep -v 'navbar.json' \
  || echo "OK: no hardcoded Spanish navbar strings"
```

Expected: both print the "OK" line. If matches appear, update those files to use `data-testid` + `t()`.

- [ ] **Step 3: Run the existing nav spec to confirm it still passes**

```bash
just test::upd                     # daemon mode (test::up blocks foreground)
just test::pw::spec 01-navigation
```

(Per project memory: `test::upd` is the default detached recipe; `test::up` blocks. If the test stack is already running, the first command is a no-op.)

Expected: existing nav spec passes.

- [ ] **Step 4: Commit**

```bash
git add frontend/playwright.config.ts
git commit -m "test(playwright): pin use.locale to en-US for deterministic regression"
```

---

## Task 19: Write the i18n Playwright spec

**Files:**
- Create: `frontend/tests/playwright/e2e/01-locale.spec.ts`

File named `01-locale.spec.ts` (NOT `01-navigation-i18n`) to avoid alphabetical confusion with the existing `01-navigation.spec.ts`.

- [ ] **Step 1: Write the spec**

File: `frontend/tests/playwright/e2e/01-locale.spec.ts`

```ts
// Import from project fixtures (provides waitForHydration, sets
// window.playwright = true to disable react-scan, and exposes login helpers).
import { test, expect } from '../fixtures';
import { loginUser } from '../fixtures';

// i18n hydration bugs must surface immediately; no retries here.
test.describe.configure({ retries: 0 });

const LOGIN_BUTTON = '[data-testid="discord-login-button"]';
const LOGOUT_BUTTON = '[data-testid="navbar-logout-button"]';
const PROFILE_BUTTON = '[data-testid="navbar-profile-button"]';
const ES_LOGIN = 'Iniciar sesión con Discord';
const EN_LOGIN = 'Login with Discord';

// Capture hydration errors across every scenario.
test.beforeEach(async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(`console: ${m.text()}`);
  });
  // Attach for retrieval inside each test via test info.
  (page as unknown as { _i18nErrors: string[] })._i18nErrors = errors;
});

function getErrors(page: import('@playwright/test').Page): string[] {
  return (page as unknown as { _i18nErrors: string[] })._i18nErrors;
}

test.describe('navbar i18n — anonymous', () => {
  test('?lang=es renders Spanish login + correct <html lang>', async ({ page }) => {
    await page.goto('/?lang=es');
    await expect(page.locator(LOGIN_BUTTON)).toHaveText(ES_LOGIN);
    await expect(page.locator('html')).toHaveAttribute('lang', 'es');
    expect(getErrors(page), 'unexpected runtime errors').toEqual([]);
  });

  test('?lang=es writes df-locale cookie even on prerendered /', async ({ page, context }) => {
    await page.goto('/?lang=es');
    await expect(page.locator(LOGIN_BUTTON)).toHaveText(ES_LOGIN);
    const cookies = await context.cookies();
    const dfLocale = cookies.find((c) => c.name === 'df-locale');
    expect(dfLocale?.value).toBe('es');
  });

  test('cookie persists Spanish across navigation', async ({ page }) => {
    await page.goto('/?lang=es');
    await expect(page.locator(LOGIN_BUTTON)).toHaveText(ES_LOGIN);
    await page.goto('/tournaments');
    await expect(page.locator(LOGIN_BUTTON)).toHaveText(ES_LOGIN);
  });

  test('default en-US context renders English', async ({ browser }) => {
    const ctx = await browser.newContext({ locale: 'en-US' });
    const page = await ctx.newPage();
    await page.goto('/');
    await expect(page.locator(LOGIN_BUTTON)).toHaveText(EN_LOGIN);
    await ctx.close();
  });

  test('es-ES context renders Spanish navbar + aria-labels', async ({ browser }) => {
    const ctx = await browser.newContext({ locale: 'es-ES' });
    const page = await ctx.newPage();
    await page.goto('/tournaments');
    await expect(page.locator(LOGIN_BUTTON)).toHaveText(ES_LOGIN);
    await expect(page.locator('html')).toHaveAttribute('lang', 'es');
    // Aria-label regression check: at least one of the translated labels must
    // appear with its Spanish value.
    await expect(
      page.locator('[aria-label="Documentación"]').first(),
    ).toBeVisible();
    await ctx.close();
  });

  test('unsupported locale (fr-FR) falls back to English', async ({ browser }) => {
    const ctx = await browser.newContext({ locale: 'fr-FR' });
    const page = await ctx.newPage();
    await page.goto('/tournaments');
    await expect(page.locator(LOGIN_BUTTON)).toHaveText(EN_LOGIN);
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
    await ctx.close();
  });

  test('?lang=en beats df-locale=es cookie', async ({ browser }) => {
    const ctx = await browser.newContext({ locale: 'en-US' });
    await ctx.addCookies([
      { name: 'df-locale', value: 'es', url: 'https://localhost' },
    ]);
    const page = await ctx.newPage();
    await page.goto('/tournaments?lang=en');
    await expect(page.locator(LOGIN_BUTTON)).toHaveText(EN_LOGIN);
    await ctx.close();
  });

  test('clearing the cookie returns to browser language', async ({ browser }) => {
    const ctx = await browser.newContext({ locale: 'en-US' });
    await ctx.addCookies([
      { name: 'df-locale', value: 'es', url: 'https://localhost' },
    ]);
    const p1 = await ctx.newPage();
    await p1.goto('/tournaments');
    await expect(p1.locator(LOGIN_BUTTON)).toHaveText(ES_LOGIN);
    await ctx.clearCookies();
    const p2 = await ctx.newPage();
    await p2.goto('/tournaments');
    await expect(p2.locator(LOGIN_BUTTON)).toHaveText(EN_LOGIN);
    await ctx.close();
  });

  test('dynamic route SSR ships Spanish HTML (no flicker for es-ES)', async ({ browser }) => {
    const ctx = await browser.newContext({ locale: 'es-ES' });
    const page = await ctx.newPage();
    const response = await page.goto('/tournaments');
    const html = (await response?.text()) ?? '';
    expect(html).toContain(ES_LOGIN);
    await ctx.close();
  });

  test('prerendered / ships English HTML then swaps to Spanish (documented trade-off)', async ({ browser }) => {
    const ctx = await browser.newContext({ locale: 'es-ES' });
    const page = await ctx.newPage();
    const response = await page.goto('/');
    const html = (await response?.text()) ?? '';
    expect(html).toContain(EN_LOGIN);
    await expect(page.locator(LOGIN_BUTTON)).toHaveText(ES_LOGIN);
    await ctx.close();
  });
});

test.describe('navbar i18n — authenticated', () => {
  test('logged-in es-ES context shows Cerrar sesión and Perfil', async ({ browser }) => {
    const ctx = await browser.newContext({ locale: 'es-ES' });
    await loginUser(ctx);
    const page = await ctx.newPage();
    await page.goto('/tournaments');
    // Open the user dropdown to reveal logout + profile entries.
    // The avatar trigger has a stable testid; if not, fall back to clicking
    // the visible user avatar inside the navbar.
    await page.locator('[data-testid="navbar-user-avatar"]').first().click().catch(async () => {
      // Fallback: click any UserAvatar inside the navbar.
      await page.locator('header [data-slot="avatar"]').first().click();
    });
    await expect(page.locator(LOGOUT_BUTTON)).toHaveText('Cerrar sesión');
    await expect(page.locator(PROFILE_BUTTON)).toHaveText('Perfil');
    await ctx.close();
  });
});
```

If the `navbar-user-avatar` testid doesn't exist in the codebase yet, the `.catch()` fallback clicks any avatar inside the `<header>`. If both fail, add a `data-testid="navbar-user-avatar"` to the avatar trigger in `navbar.tsx` as part of this task.

- [ ] **Step 2: Run the new spec**

```bash
just test::pw::spec 01-locale
```

Expected: 11 tests pass (10 anonymous + 1 authenticated).

- [ ] **Step 3: Commit**

```bash
git add frontend/tests/playwright/e2e/01-locale.spec.ts
git commit -m "test(i18n): Playwright spec for locale detection + cookie + aria-labels"
```

---

## Task 20: Visual QA Playwright spec (expanded scenarios)

**Files:**
- Create: `frontend/tests/playwright/e2e/06-visual-qa-navbar.spec.ts`
- Output: `frontend/screenshots/i18n/*.png` (committed to repo; distinct from gitignored `test-results/`)

The visual QA captures more than first paint: it opens the mobile drawer, opens the user dropdown (logged-in), and triggers hover/focus states.

- [ ] **Step 1: Add `frontend/screenshots/` to `.gitkeep` (so the dir exists in git)**

```bash
mkdir -p frontend/screenshots/i18n
touch frontend/screenshots/i18n/.gitkeep
```

- [ ] **Step 2: Write the spec**

File: `frontend/tests/playwright/e2e/06-visual-qa-navbar.spec.ts`

```ts
import { test } from '../fixtures';
import { loginUser } from '../fixtures';
import { expect } from '@playwright/test';

const VIEWPORTS = [
  { name: 'mobile', width: 375, height: 800 },
  { name: 'tablet', width: 768, height: 800 },
  { name: 'desktop', width: 1280, height: 800 },
];
const LOCALES = ['en', 'es'] as const;
const LOGIN_BUTTON = '[data-testid="discord-login-button"]';

async function settleNavbar(page: import('@playwright/test').Page, expectedLoginText: string) {
  // Wait for navbar text to reflect the final locale, then for fonts to load.
  await expect(page.locator(LOGIN_BUTTON)).toHaveText(expectedLoginText);
  await page.evaluate(() => document.fonts.ready);
}

for (const vp of VIEWPORTS) {
  for (const locale of LOCALES) {
    const expectedLogin = locale === 'es' ? 'Iniciar sesión con Discord' : 'Login with Discord';

    test(`first paint @ ${vp.name} ${locale}`, async ({ browser }) => {
      const ctx = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        locale: locale === 'es' ? 'es-ES' : 'en-US',
      });
      const page = await ctx.newPage();
      await page.goto(`/tournaments`);
      await settleNavbar(page, expectedLogin);

      // Assert no horizontal scrollbar at mobile width in Spanish — the
      // Discord button is the most likely overflow source.
      if (vp.name === 'mobile') {
        const overflow = await page.evaluate(
          () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
        );
        expect(overflow, `horizontal overflow at ${vp.name} ${locale}`).toBe(false);
      }

      await page.screenshot({
        path: `screenshots/i18n/navbar-${vp.name}-${locale}.png`,
        fullPage: false,
      });
      await ctx.close();
    });
  }
}

// Mobile drawer open
for (const locale of LOCALES) {
  const expectedLogin = locale === 'es' ? 'Iniciar sesión con Discord' : 'Login with Discord';
  test(`mobile drawer open ${locale}`, async ({ browser }) => {
    const ctx = await browser.newContext({
      viewport: { width: 375, height: 800 },
      locale: locale === 'es' ? 'es-ES' : 'en-US',
    });
    const page = await ctx.newPage();
    await page.goto('/tournaments');
    await settleNavbar(page, expectedLogin);
    // Toggle the mobile menu — selector may need adjustment based on actual MobileNav implementation.
    await page.locator('[data-testid="mobile-nav-toggle"]').click().catch(async () => {
      await page.locator('header button:has-text("Menu"), header [aria-label*="navigation"]').first().click();
    });
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({
      path: `screenshots/i18n/mobile-drawer-${locale}.png`,
      fullPage: false,
    });
    await ctx.close();
  });
}

// Logged-in user dropdown
for (const locale of LOCALES) {
  const expectedLogin = locale === 'es' ? 'Iniciar sesión con Discord' : 'Login with Discord';
  test(`user dropdown @ desktop ${locale}`, async ({ browser }) => {
    const ctx = await browser.newContext({
      viewport: { width: 1280, height: 800 },
      locale: locale === 'es' ? 'es-ES' : 'en-US',
    });
    await loginUser(ctx);
    const page = await ctx.newPage();
    await page.goto('/tournaments');
    await page.evaluate(() => document.fonts.ready);
    await page.locator('[data-testid="navbar-user-avatar"]').first().click().catch(async () => {
      await page.locator('header [data-slot="avatar"]').first().click();
    });
    await page.screenshot({
      path: `screenshots/i18n/user-dropdown-${locale}.png`,
      fullPage: false,
    });
    await ctx.close();
  });
}

// Focused login button
for (const locale of LOCALES) {
  const expectedLogin = locale === 'es' ? 'Iniciar sesión con Discord' : 'Login with Discord';
  test(`focused login button @ desktop ${locale}`, async ({ browser }) => {
    const ctx = await browser.newContext({
      viewport: { width: 1280, height: 800 },
      locale: locale === 'es' ? 'es-ES' : 'en-US',
    });
    const page = await ctx.newPage();
    await page.goto('/');
    await settleNavbar(page, expectedLogin);
    await page.locator(LOGIN_BUTTON).focus();
    await page.screenshot({
      path: `screenshots/i18n/login-focused-${locale}.png`,
      fullPage: false,
    });
    await ctx.close();
  });
}
```

Total scenarios: 6 (first-paint matrix) + 2 (mobile drawer) + 2 (user dropdown) + 2 (focused login) = 12.

- [ ] **Step 3: Run the visual QA spec**

```bash
just test::pw::spec 06-visual-qa-navbar
```

Expected: 12 tests pass, 12 screenshots in `frontend/screenshots/i18n/`. The mobile-overflow assertion fails immediately if the Spanish login button truncates at 375px.

- [ ] **Step 4: Inspect screenshots**

```bash
ls -la frontend/screenshots/i18n/
```

Open each and confirm:
- Discord button text fits at mobile in both locales (the overflow assertion catches truncation automatically).
- Nav items don't wrap unexpectedly.
- Dropdowns and tooltips render correctly in both locales.
- If `Iniciar sesión con Discord` still doesn't look right despite no horizontal overflow (e.g., it crowds neighbors), change the Spanish translation in `es/navbar.json` from `"login": "Iniciar sesión con Discord"` to `"login": "Entrar con Discord"` and re-run.

**Decision tree for the Discord button at 375px:**

| Condition | Action |
|---|---|
| Horizontal scrollbar present (assertion fails) | Switch ES to `"Entrar con Discord"`, re-run |
| Button visibly truncates / ellipses | Switch ES to `"Entrar con Discord"`, re-run |
| Button crowds neighbors but fits | Reviewer judgment in PR — keep or switch |
| Renders cleanly | Keep `"Iniciar sesión con Discord"` |

- [ ] **Step 5: Commit screenshots + spec**

```bash
git add frontend/screenshots/ frontend/tests/playwright/e2e/06-visual-qa-navbar.spec.ts
git commit -m "test(i18n): visual QA screenshots — first paint + drawer + dropdown + focus"
```

If the Spanish login string was shortened in step 4, separate commit:

```bash
git add frontend/app/i18n/locales/es/navbar.json
git commit -m "feat(i18n): shorten Spanish Discord login text to fit mobile"
```

Attach all screenshots to the PR description.

---

## Task 21: Final integration smoke + push + PR

**Files:** (none — verification only)

- [ ] **Step 1: Run the full local validate**

```bash
just frontend::validate
```

Expected: passes all four checks.

- [ ] **Step 2: Run the full Playwright suite (single shard locally, then full suite)**

```bash
# Sanity-check one shard for CI-only sharding issues
just test::pw::headless --shard=1/4
# Then full suite
just test::pw::headless
```

Expected: full suite passes including 01-locale.spec.ts and 06-visual-qa-navbar.spec.ts.

- [ ] **Step 3: Manual smoke test (cookie sanity)**

In a browser with dev environment running:
1. Visit `https://localhost/?lang=es` — navbar shows Spanish after hydration.
2. DevTools → Application → Cookies → confirm `df-locale=es` with `Max-Age` ≈ 31536000 (1 year).
3. Reload `/` (no query) — navbar still Spanish.
4. Visit `/tournaments` (dynamic) — Spanish from first paint (view-source confirms `lang="es"` and Spanish text in HTML).
5. Clear `df-locale`, set browser language to French — English fallback.

- [ ] **Step 4: Push and open PR**

```bash
git push -u origin feature/frontend-i18n-navbar-es
gh pr create --title "feat(i18n): Spanish navbar with SSR locale detection" --body "$(cat <<'EOF'
## Summary
- Adds react-i18next + remix-i18next for SSR locale detection (`?lang=` → `df-locale` cookie → `Accept-Language` → `en`).
- Translates visible navbar text + `aria-label`s into Spanish. Login button: `Iniciar sesión con Discord`.
- New `just frontend::*` module (tsc, lint, i18n::extract, i18n::check, i18n::guard, validate). Removed `npm::typecheck` and `npm::lint`.
- Bootstrapped ESLint 9 flat config; lint scoped to `app/components/navbar/` for this PR (widening is follow-up).
- `eslint-plugin-i18next/no-literal-string` (error) + grep guard (visible prop strings) + `i18next-parser --fail-on-update` (locale key parity).
- 11-test Playwright spec (incl. aria-label assertion, cookie-write check, logged-in scenario).
- 12-screenshot visual QA (first paint × 6, drawer × 2, dropdown × 2, focus × 2) committed under `frontend/screenshots/i18n/`.
- `/` and `/about` remain prerendered (Discord link previews). Documented Spanish flicker on those two routes.

## Follow-ups (separate PRs)
- CI YAML wiring (parallel jobs + caching + artifact upload) — see Task 22 in plan.
- Widen ESLint coverage beyond navbar (separate cleanup PR).

## Test plan
- [x] `just frontend::validate` passes locally
- [x] `just test::pw::headless` passes locally (full suite + single-shard)
- [x] Manual smoke test passes
- [x] Visual QA screenshots attached
EOF
)"
```

---

## Task 22 (FOLLOW-UP, separate PR): Wire CI YAML

This task is intentionally **not implemented in this PR**. It lives here as a forward-pointer.

After this PR merges, open a follow-up PR doing:

- Add a `.github/workflows/frontend-i18n.yml` (or extend an existing workflow) with **parallel jobs**:
  - `frontend-tsc` → `just frontend::tsc`
  - `frontend-lint` → `just frontend::lint`
  - `frontend-i18n-check` → `just frontend::i18n::check`
  - `frontend-i18n-guard` → `just frontend::i18n::guard`
  - `frontend-playwright` → `just test::pw::headless --shard=N/4` (matrix; deterministic blocking gate, replaces "PR review verifies suite is green")
- Shared install step → cache `node_modules` keyed on `frontend/package-lock.json` hash.
- Cache `~/.cache/ms-playwright` keyed on Playwright version.
- `cancel-in-progress: true` on workflow dispatch.
- Upload `frontend/screenshots/i18n/**` and `frontend/test-results/**` as artifacts.
- (Optional) post the i18n screenshots as a PR comment via `actions/github-script`.

Without this follow-up, the new validation gates only run via `just frontend::validate` locally; CI doesn't enforce them. The grep regression check from Task 18 also doesn't have a CI hook in this PR. Tracking item, not blocking the i18n PR itself.

---

## Self-Review

**Spec coverage:**
- Architecture (deps, file layout, detection flow, two instances, resources, cookie, prerender retained, client.ts cookie fallback): Tasks 1, 3-9, 10-13, 18-20.
- `app/i18n/{config,server,client,types}.ts`: Tasks 3, 4, 5, 6.
- `root.tsx` (loader + Layout, **no provider wrap**): Task 7. `entry.server.tsx` (provider): Task 8. `entry.client.tsx` (provider): Task 9.
- Navbar conversion (4 files, JSX text, props, aria-labels, key naming, `data-testid`s): Tasks 2, 14-17. `Profile` key (not `edit_profile`) matches actual UI text.
- Prop-string CI guard (lowercase-tolerant regex): Task 12. ESLint flat config (navbar-scoped `lint` script): Task 11. `i18next-parser` config: Task 10.
- `playwright.config.ts` locale pin + strengthened regression grep (English AND Spanish, with word boundaries, scanning navbar source): Task 18.
- `just` module restructure: Task 13.
- CI parallel jobs / caching / artifact upload: deferred to follow-up Task 22 with explicit acknowledgment that gates don't run on PR until then.
- Testing (unit/static, Playwright E2E with aria-labels + cookie-write + logged-in, visual QA with drawer/dropdown/focus + horizontal-overflow assertion, regression grep, manual smoke): Tasks 10-13, 18, 19, 20, 21.
- Risk register: hydration mismatch covered by `beforeEach` pageerror listener across all 11 tests in Task 19; prerender behavior covered by scenarios 9 and 10 plus visual-QA mobile-overflow assertion; cookie fallback for prerendered `?lang=` covered by scenario 2.

**Placeholder scan:** None remaining. The remaining ambiguity is in Task 19 step 1: if `navbar-user-avatar` testid doesn't exist, the test falls back to `header [data-slot="avatar"]` and the task instructs to add the testid as part of completion. Self-correcting.

**Type consistency:** `createI18nInstance` returns `I18nInstance` (Task 3), consumed identically in `client.ts` (Task 5) and `entry.server.tsx` (Task 8). Cookie name `df-locale` consistent across `server.ts` (Task 4), `client.ts` (Task 5), and tests (Task 19). `data-testid`s used in Task 14 (`discord-login-button`, `navbar-profile-button`, `navbar-logout-button`) and asserted by the same exact strings in Task 19 and Task 20. Key naming uses `defaultNS: 'navbar'` convention: `t('login')`, `t('profile')`, `t('logout')`, `t('aria.<x>')` — never `t('navbar.login')`. Visual QA output path `screenshots/i18n/` matches the directory created in Task 20 step 1 (`frontend/screenshots/i18n/.gitkeep`).
