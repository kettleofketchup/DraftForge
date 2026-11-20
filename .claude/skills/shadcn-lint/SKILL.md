---
name: shadcn-lint
description: 'The @shadcn/lint design-system gate for frontend/ (ESLint backend, its own config). Use when a commit or CI fails with `shadcn/...`, when the shadcn-lint suppressions baseline needs pruning, when adding a colour or class to JSX, or when touching frontend/eslint.shadcn.config.js. Triggers "no-raw-colors", "no-unknown-classes", "shadcn lint", "suppressions left that do not occur anymore".'
---

# shadcn design-system lint

Design-system rules from [`@shadcn/lint`](https://github.com/shadcn-ui/lint), run by ESLint
with its **own** config, `frontend/eslint.shadcn.config.js`. It does not touch
`eslint.config.js` or `npm run lint` (navbar-scoped i18n rollout).

```bash
just frontend::lint-shadcn         # == npm --prefix frontend run lint:shadcn
just frontend::lint-shadcn-prune   # after fixing baselined violations
```

## Enforced

| Rule | Catches |
| --- | --- |
| `shadcn/no-raw-colors` | Raw palette classes (`text-green-500`, `bg-slate-900`) and hex values instead of brand tokens. Same policy as the `brand` skill, now machine-checked. |
| `shadcn/no-unknown-classes` | Classes Tailwind emits **no CSS** for: `align-center`, `justify-left`, `items-top`, `3xl:*` (no such breakpoint), `prose*` (`@tailwindcss/typography` is not installed). Each hit is a silent styling bug. Zero baseline entries: every hit fails. |
| `draftforge/use-display-name` | A person-name field (`username`, `nickname`, `discordNickname`, `guildNickname`, `discordUsername`, `global_name`) shown to a person without `DisplayName`: JSX children, user-facing attributes (`title`, `alt`, `aria-label`, `placeholder`, `label`), and strings built by template literals or `+` (toasts, confirms, team names). Not flagged: a ternary *test*, logger calls (`log.*`, `logger.*`, `console.*`), `data-*`, `key`, `id`, `className`, links and query keys, where the raw username is correct. |
| `draftforge/use-user-avatar` | `<AvatarImage>` whose `src` reads a user's avatar (`avatar`, `avatarUrl`, `claimer_avatar`, `user_avatar`, or a local `avatar`/`avatarUrl`). Use `<UserAvatar user={…} />` for the shared fallback, sizes and Discord URL handling. Non-user images (org logos) are not flagged. |
| `draftforge/no-display-org-arg` | `DisplayName(x, …, org)`. The org is derived from the current page (`lib/displayOrg.ts`), so call `DisplayName(x)`; a deliberate override gets a line-level disable with a reason. Off in tests. |
| `draftforge/no-user-reshape` | `<UserAvatar user={{ pk: x.pk, username: x.username, … }} />` copying same-named fields from one object (or `pk` from `user_id`/`user`/`id`). Pass `user={x}`; `UserAvatar` resolves the user by id and fills the rest from the user cache. Translations such as `{ username: payload.captain_name }` are not flagged. |
| `draftforge/no-direct-name-resolver` | Calling `resolveDisplayName` or `AvatarUrl` outside the helpers. Use `DisplayName(user)` / `<UserAvatar user={…} />`. Off in tests. |
| `draftforge/no-avatar-fallback` | A raw `<Avatar>` branch beside a `<UserAvatar>` (`captain ? <UserAvatar …/> : <Avatar>…</Avatar>`), and `<AvatarFallback>` built from a person's name (`…username`, `…nickname`, a `displayName`/`username`/`nickname` variable, or `DisplayName(…)`). `UserAvatar` renders the no-user fallback itself: pass `fallbackName` for the initials when there is no user. Team initials (`team.name`) are not flagged. |
| `draftforge/no-raw-color-strings` | Raw palette classes in **any** string, for the ones `no-raw-colors` cannot trace to a `className`: lookup maps (`{ str: 'bg-red-900/40' }`), arrays, function returns, unused constants, `ui/buttons/styles.ts`. The `dedupe-raw-colors` processor drops its report when `no-raw-colors` already reported the same class on the same lines, so each class counts once. Off in tests. |
| `draftforge/no-arbitrary-color-literals` | A colour literal (`#hex`, `rgb()`/`rgba()`, `hsl()`, `oklch()`, ...) inside a Tailwind arbitrary value or property, in any string: `shadow-[inset_0_0_120px_rgba(239,68,68,0.45)]`, `text-[#5865F2]`, a `var(--x, rgba(...))` fallback. Neither palette rule reads arbitrary values. Use `var(--color-<token>)`, or `color-mix(in_oklab,var(--color-<token>)_N%,transparent)` for alpha. Pure black and white (`rgba(0,0,0,a)`, `#fff`) stay allowed for neutral shadows, like `text-white`. Off in tests. |

How to render people correctly, and the fix for each person `draftforge/*` error, is in
[`frontend-development/resources/users.md`](../frontend-development/resources/users.md);
every error message links to its section there.

The `draftforge/*` rules are local (`frontend/eslint-rules/`, combined in `index.js`; tests in
`frontend/tests/unit/eslint-*.test.ts`). The person rules are off in the helpers that implement
them (`UserAvatar.tsx`, `avatar.tsx`, `lib/userDisplayName.ts`, `lib/displayOrg.ts`, `ui/**`). When a screen deliberately shows one specific
field (an `@handle`, a labelled "Username:" row, a Discord member picker), opt out on that
line with a reason: `// eslint-disable-next-line draftforge/use-display-name -- shows the handle`.

To fix a `no-raw-colors` hit, choose the token by meaning from THEMING-GUIDE.md "Domain
Colors" (`text-radiant`, `bg-ban-surface/60`, `fill-pos-carry`, `bg-role-admin`, ...) or
its generic table (`success`, `error`, `base-*`). The rule's "nearest theme tokens" hint
matches shade only and can name the wrong meaning. A new meaning gets a token in the
"Domain colors" block of `app/app.css`, not a raw class.

Runtime hook classes that are not Tailwind utilities go in the rule's `allow` list
(`nodrag`/`nopan` for React Flow, `toaster` for sonner, `spinner` for an inline `<style>`).
Add one only for a class some JS or CSS actually reads; a typo belongs in the fix, not the list.

Off: `no-restyle` (className on primitives is the documented brand pattern),
`no-inline-styles` (the brand guide allows dynamic computed styles),
`no-arbitrary-values`, `require-static-classes` (fires on `cn("base", cond && "x")`).
Enabling one is a design decision; regenerate the baseline in the same PR.

## The baseline

Existing violations are recorded per file and rule in
`frontend/shadcn-lint-suppressions.json` (ESLint bulk suppressions). It only shrinks:

- A **new** violation fails, including one more in a file that already has some.
- A **fixed** violation also fails ("suppressions left that do not occur anymore") until
  you run `just frontend::lint-shadcn-prune` and commit the smaller file.

Never hand-edit it, and never regrow it with `--suppress-all` to get a PR green; fix the
class. It is generated, so it is excluded from prettier and `end-of-file-fixer`.

## Where it runs

- **pre-commit:** `frontend-shadcn-lint` lints only staged `frontend/app/**` sources
  (`frontend/scripts/shadcn-lint-files.sh`); a change to the config or baseline lints all of `app/`.
- **CI:** `.github/workflows/frontend-shadcn-lint.yml` lints all of `app/` on PRs touching `frontend/`.
- **`just frontend::validate`** includes it.

## Changing the config

`eslint-disable` comments elsewhere name `react-hooks`, `@typescript-eslint` and `i18next`
rules, so those plugins are registered with no rules on; without them ESLint errors with
"Definition for rule ... was not found". Keep that if you add plugins to `eslint.config.js`
that source files disable inline.

Check a change bites rather than passing vacuously:

```bash
cd frontend
printf 'export const C = () => <div className="bg-red-500 align-center" />;\n' > app/zz-canary.tsx
npm run lint:shadcn; echo "exit=$?"   # expect 2 errors and exit=1
rm app/zz-canary.tsx
```

## Related

- `brand` — the design system itself; it wins where the two disagree.
