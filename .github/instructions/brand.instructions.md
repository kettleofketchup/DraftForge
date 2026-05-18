---
applyTo: "frontend/app/components/**,frontend/app/routes/**,frontend/app/features/**,frontend/app/**/*.css"
---

# DraftForge brand & theming

Canonical: `.claude/skills/brand/SKILL.md` and `docs/THEMING-GUIDE.md` (single source of truth for palette, button system, base scale, gradients, glow effects). DraftForge visual identity = "Neon Cyber Esports" — violet/indigo primary with cyan accents, dark-mode first.

## Component substitutions (block-level rule — flag with severity `block`)

- **Raw `<button>` is forbidden.** Use `PrimaryButton`, `SecondaryButton`, `ConfirmButton`, or `EditButton` from `frontend/app/components/ui/buttons/`. Pick based on intent, not color.
- **Raw `<img>` for a user avatar is forbidden.** Use `<UserAvatar>`.
- **Hand-rolled breadcrumb markup is forbidden.** Use `<EntityBreadcrumb>`.

## Styling rules

- **No inline `style={{}}` for colors / spacing / sizing.** Move to Tailwind classes or to the brand style constants in `frontend/app/components/ui/buttons/styles.ts` (`brandGradient`, `brandSecondary`, `brandBg`, `button3DBase`, etc.).
- **No hardcoded violet/slate hex values, no `bg-slate-*` / `text-slate-*`.** Use the `bg-base-*` scale and brand tokens defined in `frontend/app/app.css`.
- **No `space-x-*` / `space-y-*`.** Use `flex` + `gap-*` (or `flex flex-col gap-*`).
- **No `w-N h-N` when width and height are equal.** Use `size-N`.
- **Use `cn(...)` for conditional classes.** Don't write manual ternary template literals.

## Where to look for the canonical rule

- Palette / tokens / gradients: `frontend/app/app.css`.
- Button style constants: `frontend/app/components/ui/buttons/styles.ts`.
- Substitution table (every raw element → replacement component): `docs/theming-guide/ai/references/component-substitutions.md`.
- Severity rubric (`block` / `warn` / `nit`): `docs/theming-guide/ai/references/severity-rubric.md`.

When a brand violation is found, cite the canonical section and propose the named replacement (don't just say "use the brand button" — say *which* brand button).
