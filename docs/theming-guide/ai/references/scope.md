# Scope: In-Scope Source Trees

This skill applies to **every** file that renders DraftForge UI in the frontend. The brand is one — feature-specific or page-specific exemptions don't exist.

## In-Scope

| Tree | Purpose |
|---|---|
| `frontend/app/components/` | Shared components — `ui/`, `user/`, `events/`, etc. The shadcn primitives in `components/ui/*.tsx` are review targets when *callers* misuse them. |
| `frontend/app/components/ui/buttons/` | Brand button library (`PrimaryButton`, `SecondaryButton`, `SubmitButton`, `ConfirmButton`, `EditButton`, `NavButton`, `DestructiveButton`, `CancelButton`, plus `icons/` and domain folders). Adding a new button MUST follow the README convention. |
| `frontend/app/routes/` | React Router route components. Top-level page UI. |
| `frontend/app/features/` | Feature-scoped components and hooks. Page-specific buttons, dialogs, forms. |
| `frontend/app/app.css` | Token SSOT (CSS variables, `--primary`, `--base-*`, gradients, glows). Token additions must be reflected in `THEMING-GUIDE.md`. |
| `frontend/tailwind.config.js` | Tailwind theme extension (custom colors, `bg-base-*` scale, `--ring`). Changes here ripple through every component. |

## Out of Scope

- `frontend/app/components/ui/*.tsx` — the bare shadcn primitives (`button.tsx`, `dialog.tsx`, etc.). These define the brand contract; review here is for *callers*. Use the `ui-styling` or `shadcn` skills if changing the primitives themselves.
- Build tooling: `vite.config.ts`, `tsconfig.*.json`, `eslint.config.js`, `playwright.config.ts`.
- Generated bindings, type stubs.
- E2E tests under `frontend/tests/` — selectors are the contract, not the styling. (Exception: if a test asserts a specific brand class, that's a brand contract; review the assertion.)
- Backend Python (`backend/`), Django templates, Daphne/Channels routing.
- Docs (`docs/`), nginx config, Docker config.

## Special Cases

### Mandatory components

Two components MUST be used wherever applicable; raw markup is a `block`:

| Use case | Required component | Why |
|---|---|---|
| Showing a user's avatar | `<UserAvatar>` from `~/components/user/UserAvatar` | Handles Discord CDN, fallback initials, online indicator, captain ring, memoization. Raw `<img>` with `AvatarUrl()` is a known regression source. |
| Detail-page breadcrumb on org/league/event/series/tournament/rollcall | `<EntityBreadcrumb>` from `~/components/ui/entity-breadcrumb` | Renders the typed segment labels ("ORGANIZATION" above "DTX") and disables the last segment automatically. Manual breadcrumb nav is a `block`. |

See [`THEMING-GUIDE.md` §"Component Patterns"](../../THEMING-GUIDE.md#component-patterns) for the full mandatory list.

### Button policy

Per `THEMING-GUIDE.md` §"Button Policy": **all user-facing actions must use a brand button wrapper**, not raw `<Button>` from `~/components/ui/button`. Raw `<Button>` is reserved for **structural** uses only — dropdown triggers, combobox triggers, shadcn internals.

A raw `<Button>` with `onClick` that performs a user-facing action is a `block`.

### Dialog / AlertDialog surfaces

`Dialog` and `AlertDialog` content automatically include the `brandBg` overlay (see `THEMING-GUIDE.md` §"Brand Surface Background"). Adding `bg-gradient-to-*` to a `DialogContent` would silently strip `bg-background` (tailwind-merge group collision) — **do not do it**. Use `[background-image:var(--brand-bg)]` arbitrary property if a custom overlay is needed.

### Token vs literal

The brand uses **semantic tokens** (`bg-primary`, `bg-base-900`, `text-foreground`, `text-success`) that map to oklch values in `app.css` / `tailwind.config.js`. Raw Tailwind color classes (`bg-violet-500`, `text-slate-100`) bypass the token layer.

Exception: error surface containers explicitly use raw `red-900` / `violet-900` per `THEMING-GUIDE.md` §"Status Colors" — that's intentional, not drift. The semantic `--error` token (`rose-500`) is for inline accents only.
