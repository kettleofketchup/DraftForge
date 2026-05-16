# Theming Guide — AI References

This subtree is the AI-targeted slice of [`docs/THEMING-GUIDE.md`](../THEMING-GUIDE.md). The canonical brand content (palette, button system, status colors, gradients, glow effects, mandatory components) lives in `THEMING-GUIDE.md` and is human-first.

The pages under [`references/`](references/) are written for review automation: short, grep-friendly, full of concrete file paths and replacement snippets. The companion `brand` skill (`.claude/skills/brand/SKILL.md`) loads them on demand when reviewing or writing UI code.

## When These Pages Activate

The `brand` skill is invoked automatically by the harness in two cases:

1. The user asks for a UI review (or one is run via `/review`).
2. Editing or adding any file under `frontend/app/`.

The skill itself is short — it points back to the pages here. Update content **here** (the docs) and the skill picks up the change on next read. Do NOT duplicate review checklists or substitution tables inside the skill — keep the skill thin.

## Reference Map

| Page | Purpose |
|---|---|
| [`scope.md`](references/scope.md) | Which source trees this skill applies to. Frontend only — Django/Channels backend is out of scope. |
| [`component-substitutions.md`](references/component-substitutions.md) | Raw HTML / hand-rolled markup → DraftForge component replacement table. `<button>` → `<PrimaryButton>` / `<SecondaryButton>` / `<ConfirmButton>` / `<EditButton>` etc.; `<img>` for avatars → `<UserAvatar>`; manual breadcrumb nav → `<EntityBreadcrumb>`; structural `<Button>` exceptions. |
| [`inline-styles.md`](references/inline-styles.md) | Inline `style={{}}`, raw violet/indigo/slate Tailwind classes (`bg-violet-500`, `bg-slate-900`) instead of brand tokens (`bg-primary`, `bg-base-900`), hardcoded gradients, missing `cn()`, `space-x-*` / `space-y-*`, `w-N h-N` pairs. |
| [`review-checklist.md`](references/review-checklist.md) | Single ordered checklist to walk a diff. Each item links to the relevant section of `THEMING-GUIDE.md` for the *why*. |
| [`grep-recipes.md`](references/grep-recipes.md) | Copy-paste `rg` recipes for finding each anti-pattern across `frontend/app/`. |
| [`severity-rubric.md`](references/severity-rubric.md) | `block` / `warn` / `nit` definitions and review-output format. |
| [`scrollbars-dialogs.md`](references/scrollbars-dialogs.md) | `<ScrollArea>` inside `<DialogContent>` contract — the `overflow-hidden` clipping rule, why Radix Viewport's `size-full` needs a definite parent height, and the `-mx-6 px-6` padding-cancel trick. |

## Hidden From MkDocs Nav

These files are intentionally NOT listed in `mkdocs.yml`'s `nav:` block. MkDocs uses an explicit nav (no awesome-nav), so omitting an entry hides it from the sidebar. The pages still build and are linkable, and `THEMING-GUIDE.md` includes their content via `pymdownx.snippets` (`--8<-- "theming-guide/ai/references/<name>.md"`).

## Updating These References

Run the `/brand-update` slash command (`.claude/commands/brand-update.md`). It walks the lockstep edit of these reference files, the skill, and `THEMING-GUIDE.md`, and verifies backlinks + snippet integrity. Hand-editing one side without the other is a known drift source — don't do it.

## Backlinks

- Canonical brand guide: [`../THEMING-GUIDE.md`](../THEMING-GUIDE.md)
- Token SSOT: `frontend/app/app.css`
- Brand style constants: `frontend/app/components/ui/buttons/styles.ts`
- Buttons folder convention: `frontend/app/components/ui/buttons/README.md`
- Skill entry point: `.claude/skills/brand/SKILL.md`
- Update command: `.claude/commands/brand-update.md`
- Sibling skills that delegate here: `.claude/skills/aesthetic/SKILL.md`, `.claude/skills/ui-styling/SKILL.md`, `.claude/skills/frontend-development/SKILL.md`
