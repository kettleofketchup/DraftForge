# Frontend i18n: Spanish navbar with SSR-aware detection

**Status:** Design — awaiting implementation plan
**Date:** 2026-05-19 (revised after multi-skill review)
**Branch:** `feature/frontend-i18n-navbar-es`

## Summary

Add localization scaffolding to the React Router 7 SSR frontend. Translate the navbar (visible text **and** `aria-label`s) into Spanish, with English as the fallback. Provide a `just frontend::*` module with `tsc`, `lint`, `i18n::extract`, `i18n::check`, and `validate` recipes. Enforce "every navbar string must be translated" via `eslint-plugin-i18next` (JSX text), a CI grep guard (prop-based visible text), and `i18next-parser --fail-on-update` (key parity across locales). `/` and `/about` remain prerendered (preserves fast Discord/social link previews and edge-cacheable landing pages) — Spanish-language visitors see a brief navbar-text flicker on those two routes only, documented as the cost of preserving link-preview quality. No backend changes.

## Goals

- Working Spanish translation of all visible navbar text **and** navbar `aria-label`s, with the Discord login button as the highest-priority string.
- Server-side locale detection on every **dynamic** route via `?lang=` + `df-locale` cookie + `Accept-Language` — no English flash on hydration for any non-prerendered route.
- A `just frontend::*` workflow for type-checking, linting, and validating translation completeness.
- Automated enforcement that future code touching the navbar cannot ship untranslated literals (both JSX text via ESLint and prop-based visible text via a CI grep guard).
- ESLint flat config bootstrapped from scratch (project ships ESLint 9 dependencies but no config or `lint` npm script today).
- Layout robustness across `sm`/`md`/`lg` breakpoints in both locales (Spanish strings can be ~20% longer than English).
- Playwright suite pinned to `locale: 'en-US'` so regression behavior is deterministic regardless of host OS locale.
- Preserve fast Discord / social-card link previews and edge-cacheable static HTML for `/` and `/about` — these are kept on the `prerender` list.

## Non-goals

- Translating non-navbar components.
- Translating Tooltip JSX content beyond what already appears in navbar files.
- A user-facing language picker UI (cookie + `?lang=` are sufficient for v1).
- Backend Django i18n (`gettext_lazy`, `.po` files, `LocaleMiddleware`).
- Persisting locale to the user model or any API.
- Eliminating the navbar-text flicker on `/` and `/about` for Spanish-language visitors. (Those routes stay prerendered as English HTML; Spanish swaps in on client hydration. Bilingual prerender is the proper fix and is listed under Open follow-ups.)

## Architecture

### Dependencies

Runtime (`frontend/package.json` `dependencies`):
- `i18next` — translation engine
- `react-i18next` — React bindings (`useTranslation`, `<I18nextProvider>`)
- `remix-i18next` — server-side `Accept-Language`/cookie/query detection compatible with React Router 7

Dev (`frontend/package.json` `devDependencies`):
- `i18next-parser` — extracts `t()` calls into JSON
- `eslint-plugin-i18next` — provides the `no-literal-string` rule

### File layout

```
frontend/
  app/
    i18n/
      config.ts                 # createI18nInstance() factory
      server.ts                 # RemixI18Next instance + cookie
      client.ts                 # client singleton init
      types.ts                  # TS module augmentation for typed t()
      locales/
        en/navbar.json          # English source of truth (parser-managed)
        es/navbar.json          # Spanish translations (parser-managed)
    root.tsx                    # loader returns {locale}; <html lang={locale}>
    entry.client.tsx            # bootstraps client i18n singleton
    entry.server.tsx            # uses server i18n instance per request
  i18next-parser.config.ts      # parser config (scoped to navbar/)
  eslint.config.js              # ESLint 9 flat config (new file)
  playwright.config.ts          # MODIFIED: pin use.locale: 'en-US'
  react-router.config.ts        # UNCHANGED: prerender remains ["/", "/about"] for link previews
  tsconfig.json                 # MODIFIED: add resolveJsonModule: true if missing
  package.json                  # adds lint, i18n:extract, i18n:check, i18n:guard scripts
  scripts/
    check-navbar-prop-strings.sh  # CI grep guard for prop-based visible text
just/
  frontend/
    mod.just                    # tsc, lint, validate; mod i18n
    i18n.just                   # extract, check, guard
```

### Locale detection flow

Priority chain (server-side, via `remix-i18next`):

1. `?lang=es` query parameter (one-shot override; also sets cookie on response)
2. `df-locale` cookie (persisted user choice)
3. `Accept-Language` header (browser default)
4. `en` fallback

Detection runs in the `root.tsx` loader. The detected locale is returned in loader data and used to:
- Initialize a per-request server-side i18n instance (no shared state between requests).
- Render `<html lang={locale}>` so screen readers and CSS `:lang()` selectors see the right value.
- Sync the client-side i18n singleton via `useChangeLanguage(locale)` after hydration — guarantees no hydration mismatch.

### Two i18n instances

A factory in `app/i18n/config.ts` (`createI18nInstance(locale)`) builds an i18next instance with the given language and the bundled resources. `createInstance().use(initReactI18next)` is called **once** inside the factory. Both server and client construct instances through this factory:
- **Server**: a fresh instance per request inside `entry.server.tsx` (no cross-request leakage).
- **Client**: a singleton built in `entry.client.tsx`, reading the locale from `document.documentElement.lang`. The client does NOT re-register `initReactI18next` — the factory already did.

### Resources

Translation JSON is **bundled at build time**, not loaded over the network. Two locales × one namespace (`navbar`) is small (< 2 KB total) and bundling avoids an extra HTTP request on first paint. JSON imports require `resolveJsonModule: true` in `tsconfig.json` (verify and add if missing).

### Cookie

Name: `df-locale`. Set by `remix-i18next` on responses when the locale changes (e.g., when `?lang=es` is present).

Attributes:
- `sameSite: 'lax'`, `path: '/'`
- **`maxAge: 60 * 60 * 24 * 365`** (1 year) — persistent across visits, not session-scoped. The earlier "session cookie" framing was insufficient for the spec's own E2E test ("navigate to another route without `?lang=` → still Spanish"). Persistent is the correct semantics for "user-chosen locale."
- `secure: true` in production (set conditionally; not required in dev over plain HTTP).

### Prerender retained

`react-router.config.ts` is **unchanged**:
```ts
export default { ssr: true, prerender: ["/", "/about"] } satisfies Config;
```

Why keep prerender:
- **Discord link previews.** Discord's crawler fetches the linked URL when a user pastes it; static HTML returns in tens of milliseconds, dynamic SSR can take hundreds. For a Discord-centric Dota 2 community, every shared draft/tournament link gets faster previews.
- **Other social crawlers** (Twitter, Slack, Facebook, OG-image scrapers) similarly benefit from static HTML.
- **Resilience.** Edge-cached `/` and `/about` survive origin outages.
- **Core Web Vitals.** Better TTFB and LCP for the two highest-traffic routes; SEO ranking benefit.
- **Origin load.** Reduces SSR pressure on what are likely the most-hit routes.

Cost of keeping prerender:
- `/` and `/about` ship as static **English** HTML and cannot honor `Accept-Language` on the first byte.
- Spanish-language visitors hitting `/` or `/about` see English navbar text for the JS-hydration window (~200-1500 ms depending on bundle and device), then it swaps to Spanish.
- Crawlers (Discord, etc.) always see the English preview regardless of recipient locale — acceptable, since most link recipients are English-speaking and the preview is informational, not the live UI.

The flicker is confined to those two routes. Every other route is dynamically SSR'd and renders the correct language from first paint. Bilingual prerender (`/index.en.html` + `/index.es.html`, edge-picked by `Accept-Language`) is listed under Open follow-ups if Spanish-user UX on the landing page becomes a measurable issue.

## Code changes

### `app/i18n/config.ts`

Exports `createI18nInstance(locale: string)` returning an i18next instance configured with:
- `lng: locale`, `fallbackLng: 'en'`, `supportedLngs: ['en', 'es']`
- `ns: ['navbar']`, `defaultNS: 'navbar'`
- Static `resources` bundling `en/navbar.json` and `es/navbar.json`
- `interpolation.escapeValue: false` (React already escapes)
- `react.useSuspense: false` (simpler SSR semantics)

Internally calls `createInstance().use(initReactI18next).init({...})` — single point of registration.

### `app/i18n/server.ts`

Exports `i18nServer` — a `RemixI18Next` instance configured with:
- `supportedLanguages: ['en', 'es']`, `fallbackLanguage: 'en'`
- Detection order: `['searchParams', 'cookie', 'header']`
- `searchParamKey: 'lang'`
- Cookie via `createCookie('df-locale', { sameSite: 'lax', path: '/', maxAge: 60 * 60 * 24 * 365 })`

### `app/i18n/client.ts`

Two responsibilities, both executed before React mounts:

1. **Cookie fallback for prerendered routes.** If `?lang=<xx>` is in `location.search` and the `df-locale` cookie is missing or different, write it via `document.cookie` so subsequent navigations to dynamic routes find it. This is required because prerendered `/` and `/about` produce no server response and thus no `Set-Cookie` header.
2. **Locale resolution and singleton creation.** Compute the effective locale:
   - If `?lang=<xx>` is present and in `supportedLngs`, use it (the prerendered HTML was English, but we want the client to pick up the requested language immediately and let `useChangeLanguage` swap the navbar text on hydration).
   - Else, use `document.documentElement.lang` (set by the server for dynamic routes).
   - Fall back to `'en'`.

Then call `createI18nInstance(locale)` and export the singleton. Does NOT re-register `initReactI18next` (the factory already does).

### `app/i18n/types.ts`

```ts
import type navbar from './locales/en/navbar.json';
declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: 'navbar';
    resources: { navbar: typeof navbar };
  }
}
```

Because `defaultNS` is `'navbar'`, **call site convention is `t('login')`, NOT `t('navbar.login')`**. `useTranslation('navbar')` scopes the hook to that namespace; passing the full `navbar.login` would resolve as `t('navbar.navbar.login')`. Apply this consistently in all navbar files.

### `app/root.tsx`

Add:

```ts
import { useChangeLanguage } from 'remix-i18next/react';

export async function loader({ request }: LoaderFunctionArgs) {
  const locale = await i18nServer.getLocale(request);
  return { locale };
}

export function Layout({ children }: { children: React.ReactNode }) {
  const { locale } = useLoaderData<typeof loader>();
  useChangeLanguage(locale);
  return (
    <html lang={locale}>
      {/* ... existing head ... */}
      <body>{children}</body>
    </html>
  );
}
```

If `root.tsx` already exports a `loader`, merge the `locale` field into its existing return data rather than replacing the function.

### `app/entry.server.tsx`

Modified so the SSR render is wrapped in `<I18nextProvider i18n={createI18nInstance(locale)}>` where `locale` is read from the same `i18nServer.getLocale(request)` call. This ensures the server's React tree renders with the right language. The implementation pattern follows the `remix-i18next` README's "server-side rendering" section.

### Navbar conversion

Each navbar source file (`navbar.tsx`, `MobileNav.tsx`, `PageNavBar.tsx`, `login.tsx`) gets:

```ts
import { useTranslation } from 'react-i18next';
const { t } = useTranslation('navbar');
```

Three categories of strings to handle:

1. **JSX text nodes** (e.g. `<span>Login with Discord</span>`, `<TooltipContent>Home</TooltipContent>`) — caught by the ESLint rule; **must** be translated.
2. **Visible prop strings** (e.g. `title="Events"`, `subtitle="Sign up here"`, `label="..."`) — **not** caught by the ESLint rule (because `markupOnly: true`). Manually identified during implementation **and** enforced by a CI grep guard (see "Prop-string CI guard" below).
3. **A11y prop strings** (`aria-label`) — translated in v1 (moved into scope from v1.5 because `<html lang="es">` with English `aria-label`s causes screen readers to mispronounce English text with Spanish phonemes). Caught by removing `aria-label` from the ESLint `ignoreAttribute` list.
4. **Technical props** (`data-testid`, `className`, `href`, `to`) — never translated; stay in `ignoreAttribute`.

The asymmetry between categories (1) and (2) — JSX text vs. prop strings — is a known limitation of `eslint-plugin-i18next` when used with `markupOnly: true`. The CI grep guard (see below) closes the gap deterministically for the navbar directory.

Initial key inventory (final list produced during implementation by grepping the four navbar files):

| Key | English | Spanish | Category |
|---|---|---|---|
| `login` | Login with Discord | Iniciar sesión con Discord | JSX text |
| `signup_here` | Sign up here | Regístrate aquí | prop (subtitle) |
| `home` | Home | Inicio | JSX text + aria-label |
| `logout` | Logout | Cerrar sesión | JSX text |
| `edit_profile` | Edit Profile | Editar perfil | JSX text |
| `aria.star_github` | Star us on GitHub | Danos una estrella en GitHub | aria-label |
| `aria.documentation` | Documentation | Documentación | aria-label |
| `aria.report_bug` | Report a Bug | Reportar un problema | aria-label |
| `aria.main_nav` | Main navigation | Navegación principal | aria-label |

Spanish style: infinitive verb forms (formal, neutral), no regional dialect.

**Discord button length consideration:** "Iniciar sesión con Discord" (28 chars) is ~55% longer than "Login with Discord" (18 chars). If the button truncates at `sm` breakpoint, fall back to the shorter `"Entrar con Discord"` (19 chars) — decide during the visual QA pass.

### Prop-string CI guard

`frontend/scripts/check-navbar-prop-strings.sh` — fails CI if any of these patterns appear in navbar files outside a `t(...)` call:

```bash
#!/usr/bin/env bash
set -e
PATTERNS='(title|subtitle|label|placeholder|tooltip)="[A-Z]'
if grep -rEn "$PATTERNS" frontend/app/components/navbar/ \
    --include='*.tsx' --include='*.ts'; then
  echo "ERROR: Untranslated visible prop strings in navbar/. Wrap with t()."
  exit 1
fi
```

Surfaced as `npm run i18n:guard` and `just frontend::i18n::guard`, run by `frontend::validate` and CI. Trivial to fool with computed strings; deliberately strict for the small navbar directory.

### ESLint flat config

New file `frontend/eslint.config.js`. Wires up the already-installed plugins (`@typescript-eslint`, `react`, `react-hooks`, `react-refresh`, `react-compiler`, `prettier`) with **permissive defaults** (most rules `warn` or off) to avoid blocking on pre-existing issues across the codebase.

The strict block (note: `aria-label` removed from `ignoreAttribute`):

```js
{
  files: ['app/components/navbar/**/*.{ts,tsx}'],
  plugins: { i18next },
  rules: {
    'i18next/no-literal-string': ['error', {
      markupOnly: true,
      ignoreAttribute: ['data-testid', 'className', 'href', 'to'],
    }],
  },
}
```

`markupOnly: true` restricts the rule to JSX text — function arguments and variable assignments are not flagged. Prop-string visibility is covered by the grep guard above.

### `frontend/i18next-parser.config.ts`

```ts
export default {
  locales: ['en', 'es'],
  input: ['app/components/navbar/**/*.{ts,tsx}'],
  output: 'app/i18n/locales/$LOCALE/$NAMESPACE.json',
  defaultNamespace: 'navbar',
  keySeparator: '.',
  createOldCatalogs: false,
};
```

Scoped to `app/components/navbar/**` via the `input` field. Expanding coverage later means adding paths here and to the ESLint `overrides` block and the grep guard.

### `frontend/package.json` scripts

Add:

```json
{
  "scripts": {
    "lint": "eslint . --max-warnings 0",
    "i18n:extract": "i18next --config i18next-parser.config.ts",
    "i18n:check": "i18next --config i18next-parser.config.ts --fail-on-update",
    "i18n:guard": "scripts/check-navbar-prop-strings.sh"
  }
}
```

The input glob lives in `i18next-parser.config.ts`, not in the CLI args — single source of truth for scope.

`--max-warnings 0` ensures warnings count as failures in CI even though most rules are `warn`-level — this is intentional so we can ratchet up strictness without changing the CI invocation.

### `frontend/playwright.config.ts` changes

Pin host-OS-locale independence:

```ts
use: {
  // ... existing ...
  locale: 'en-US',
},
```

Without this, Playwright inherits the host OS locale (which on developer machines and some CI runners may not be `en-US`). The regression-check claim "existing specs run in `en-US`" only holds if we pin it.

Per-test Spanish/French scenarios in the new i18n spec use `browser.newContext({ locale: 'es-ES' })` to override.

## `just` module

### `just/frontend/mod.just`

```just
frontend := source_directory() / ".." / ".." / "frontend"

mod i18n 'i18n.just'

[group('frontend')]
tsc:
    cd "{{frontend}}" && npm run typecheck

[group('frontend')]
lint:
    cd "{{frontend}}" && npm run lint

# Aggregate validator — convenient for local dev.
# In CI, the three steps run as parallel jobs (see CI section).
[group('frontend')]
validate: tsc lint
    just frontend::i18n::check
    just frontend::i18n::guard
```

### `just/frontend/i18n.just`

```just
frontend := source_directory() / ".." / ".." / "frontend"

[group('i18n')]
extract:
    cd "{{frontend}}" && npm run i18n:extract

[group('i18n')]
check:
    cd "{{frontend}}" && npm run i18n:check

[group('i18n')]
guard:
    cd "{{frontend}}" && npm run i18n:guard
```

### Top-level `justfile`

- Add: `mod frontend 'just/frontend/mod.just'`
- Keep: `mod npm 'just/npm.just'`
- Modify `just/npm.just`: remove the `typecheck` and `lint` recipes (they move to `frontend::tsc` and `frontend::lint`); keep `install`, `dev`, `build`, and `run *args` as-is.

User-facing commands after this PR:

- `just frontend::tsc` (replaces `just npm::typecheck`)
- `just frontend::lint` (replaces `just npm::lint`)
- `just frontend::i18n::extract` — local dev, regenerates JSON
- `just frontend::i18n::check` — CI, fails on missing keys
- `just frontend::i18n::guard` — CI, fails on untranslated prop strings in navbar/
- `just frontend::validate` — runs tsc + lint + i18n::check + i18n::guard (local convenience)
- `just npm::install`, `just npm::dev`, `just npm::build`, `just npm::run *args` — unchanged

No external callers reference `just npm::typecheck` or `just npm::lint` in `.github/`, `docs/`, or other `just/` modules (verified during brainstorming via `grep -rn "npm::typecheck\|npm::lint"`).

## CI

### Job structure

`just frontend::validate` is the local convenience target. In CI, the four checks run as **parallel jobs** so failures are isolated and don't mask each other:

| Job | Command | Purpose |
|---|---|---|
| `frontend-tsc` | `just frontend::tsc` | TypeScript compile |
| `frontend-lint` | `just frontend::lint` | ESLint, including `no-literal-string` on navbar/ |
| `frontend-i18n-check` | `just frontend::i18n::check` | Parser key parity (`--fail-on-update`) |
| `frontend-i18n-guard` | `just frontend::i18n::guard` | Grep for untranslated prop strings in navbar/ |
| `frontend-playwright` | `just test::pw::headless --shard=N/4` | Full Playwright suite, deterministic blocking gate |

All five run in parallel after a shared `npm install` setup job. The Playwright job is a **blocking required check** for merge — not "PR review verifies the suite is green." Existing Playwright specs continue to pass because of the pinned `use.locale: 'en-US'` (see Playwright config change above) plus the fact that the existing nav spec uses `data-testid` not visible text.

### Caching

- `node_modules`: cache key derived from `frontend/package-lock.json` hash. Shared across all five jobs.
- Playwright browsers: cache `~/.cache/ms-playwright` keyed on the Playwright version in `package-lock.json`.

CI runner interruption (force-push during in-flight pipeline) should cancel obsolete runs (`interruptible: true` on GitLab; `cancel-in-progress: true` on GitHub Actions).

## Testing

### Unit / static

Same four checks as the CI jobs above, runnable locally via `just frontend::validate`.

### Playwright E2E

**File path:** `frontend/tests/playwright/e2e/01-navigation-i18n.spec.ts` (sibling of existing `01-navigation.spec.ts`, NOT inside a new `01-navigation/` directory).

**Per-test config:** `test.use({ retries: 0 })` — i18n hydration bugs must surface immediately; retries would mask them. This is a deliberate divergence from the suite-wide `retries: 2`.

**Scenarios (all anonymous — no login fixture):**

| # | Setup | Assertion |
|---|---|---|
| 1 | Visit `/?lang=es` | `[data-testid="discord-login-button"]` has text `Iniciar sesión con Discord` |
| 2 | Visit `/?lang=es`, then click any nav link | New page still in Spanish (cookie persisted) |
| 3 | New context `locale: 'en-US'`, no `?lang=` | Login button in English |
| 4 | New context `locale: 'es-ES'`, no `?lang=` | Login button in Spanish |
| 5 | New context `locale: 'fr-FR'`, no `?lang=` | English fallback (French not in `supportedLngs`) |
| 6 | Visit `/?lang=es` | `await expect(page.locator('html')).toHaveAttribute('lang', 'es')` |
| 7 | Set `df-locale=es` cookie, visit `/?lang=en` | English (query beats cookie) |
| 8 | Set `df-locale=es`, clear cookie via `context.clearCookies()`, visit `/` with `locale: 'en-US'` | English (cookie cleared) |
| 9 | Hook `page.on('pageerror')` and `page.on('console', m => m.type() === 'error')` during scenarios 1-5 | Zero errors (hydration mismatch detector) |
| 10 | Visit a dynamic route (e.g. `/tournaments`) with new context `locale: 'es-ES'` | Spanish navbar in first HTML response (no flicker) — server SSR honored `Accept-Language` |
| 11 | Visit prerendered `/` with new context `locale: 'es-ES'` | First HTML response contains English navbar (prerendered); after hydration, navbar text is Spanish. Asserts the documented trade-off without timing the flicker. |

Scenarios 10 and 11 pin the documented behavior: dynamic routes never flicker; prerendered routes flicker by design. If someone adds another route to `prerender` later without thinking about i18n, scenario 11's pattern catches the regression.

**`data-testid` addition:** Add `data-testid="discord-login-button"` to the Discord login button in `login.tsx` so assertions target the element deterministically and don't change when copy changes (per the project's locator policy).

### Regression check

The existing nav spec (`tests/playwright/e2e/01-navigation.spec.ts`) uses `data-testid` selectors, not text — already locale-safe. **But** to prove no other spec asserts English navbar copy, the implementation must run:

```bash
grep -rn "Login with Discord\|Sign up here\|Logout\|Edit Profile" frontend/tests/playwright/e2e/
```

Expected output: empty (no matches). Non-empty output blocks the PR and the offending specs must be updated to use `data-testid` + locale-aware text assertions.

Combined with the pinned `playwright.config.ts` `use.locale: 'en-US'`, the regression check is deterministic.

### Visual QA

Required before merge — Playwright screenshots at three viewports in both locales:

| Viewport | Width | Locales |
|---|---|---|
| Mobile | 375 | en, es |
| Tablet | 768 | en, es |
| Desktop | 1280 | en, es |

Six screenshots total, attached to the PR. Reviewer checks for:
- No text overflow on the Discord button (decide between full Spanish vs. `"Entrar con Discord"` if it truncates at 375).
- Nav items don't wrap unexpectedly.
- Drop-down menu items render correctly in both locales.

Automated as a single Playwright spec that emits screenshots, executed in CI but not gating (artifacts attached for human review).

### Local developer workflow

1. Developer adds `t('new_thing')` to a navbar component.
2. Runs `just frontend::i18n::extract` — parser writes `"new_thing": "new_thing"` to both `en/navbar.json` and `es/navbar.json`.
3. Developer fills in the real English and Spanish.
4. Runs `just frontend::validate` — passes.
5. Pushes.

### Manual smoke test (PR description)

- `/?lang=es` → Spanish navbar, no English flash
- DevTools cookies → `df-locale=es` with `Max-Age` ~31 million seconds
- Reload `/` (no query) → still Spanish
- Clear `df-locale`, browser language `fr-FR` → English fallback

## Open follow-ups (not in this PR)

- Translate non-navbar components — broaden ESLint `overrides`, parser `input` globs, and grep guard as each area gets translated.
- Build a language picker UI (a React Router action that writes the cookie and calls `useChangeLanguage`; do NOT add a `locale` slice to Zustand — the loader/cookie remains source of truth).
- Bilingual prerender for `/` and `/about` to eliminate the navbar flicker for Spanish-language visitors (build `/index.en.html` + `/index.es.html`, pick at the edge / via a small CDN function based on `Accept-Language`). Defer until Spanish-user volume justifies the build-time complexity.
- Backend Django i18n for emails, validation errors, and notifications — separate spec.
- Custom ESLint rule that catches visible-prop literals by name (replaces the grep guard with proper AST analysis).

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `remix-i18next` ergonomics differ subtly under React Router 7 (originally Remix) | Medium | Low | Verify against current `remix-i18next` docs during implementation; if blocked, fall back to manual loader-based detection (same flow, ~20 lines extra) |
| Bootstrapping ESLint flat config surfaces hundreds of warnings | High | Low | Most rules set to `warn` or off; only navbar-scoped `i18next/no-literal-string` is `error`; `--max-warnings 0` is the ratchet for future tightening |
| Hydration mismatch on the `<html lang>` attribute if server detect disagrees with client | Low | Medium | `useChangeLanguage(locale)` syncs the client to server-decided locale before any user-visible rendering; covered by Playwright scenarios 6 and 9 |
| Existing Playwright specs accidentally trip the Spanish translation | Low | Medium | Pinned `use.locale: 'en-US'` in `playwright.config.ts`; grep gate confirms no spec asserts English navbar text; existing nav spec uses `data-testid` |
| Spanish visitors see navbar-text flicker on `/` and `/about` | Medium (for Spanish users hitting those routes) | Low | Prerender retained for link-preview speed; flicker is confined to two routes; rest of app renders Spanish from first paint. Bilingual prerender is the proper follow-up if this becomes a measurable problem. |
| `?lang=es` on prerendered `/` doesn't set the `df-locale` cookie (no server response runs) | Medium | Low | Add a client-side fallback in `app/i18n/client.ts`: if `URLSearchParams` has `lang` and the cookie doesn't match, write the cookie via `document.cookie = ...` before React mounts. Cookie persistence still works the next time the user lands on any dynamic route. |
| Discord login button text overflows on mobile in Spanish | Medium | Low | Visual QA gate at 375px in both locales; fall back to `"Entrar con Discord"` if it truncates |
| `aria-label` translations introduce unintended text changes that break old specs | Low | Medium | No existing spec asserts navbar `aria-label`s (verified via `grep -rn 'aria-label' frontend/tests/playwright/`) — confirm during implementation |
