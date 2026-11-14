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
