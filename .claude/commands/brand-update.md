---
description: Update the DraftForge brand skill and the docs theming-guide AI references in lockstep
argument-hint: [what to add/change/remove]
---

# /brand-update — Update the DraftForge Brand Review Surface

Update the brand-review documentation **and** the brand skill in one pass so they never drift. This is the only sanctioned way to evolve the brand-review rules — never edit one side without the other.

User instruction:
<prompt>$ARGUMENTS</prompt>

## Files Under Management

This command edits ONLY these files. Do not edit any other UI/component file in this pass — those go through a normal review.

| File | Role |
|---|---|
| `docs/THEMING-GUIDE.md` | Canonical brand guide (human-first). Edit only when a *fundamental* rule changes (palette, button policy, status colors, mandatory components, status patterns, glow effects, dialog surface contract). The `## References` section at the bottom must keep the existing `pymdownx.snippets` blocks (`--8<-- "theming-guide/ai/references/<name>.md"`) intact — that's how AI references show up in the rendered guide. |
| `docs/theming-guide/ai/index.md` | AI-references hub (hidden from MkDocs nav by simply not being listed in `mkdocs.yml`). Update the reference map table when adding/removing reference files. |
| `docs/theming-guide/ai/references/scope.md` | In-scope source trees + special cases (mandatory components, button policy, dialog surface exception). Edit when scope changes. |
| `docs/theming-guide/ai/references/component-substitutions.md` | Raw HTML / hand-rolled markup → DraftForge component replacement table. Buttons, avatars, breadcrumbs, dialogs, status indicators. |
| `docs/theming-guide/ai/references/inline-styles.md` | `style={{}}`, raw violet/slate Tailwind classes, hardcoded gradients/hex/oklch, `space-x-*`, `w-N h-N`, `cn()`, ad-hoc glow. |
| `docs/theming-guide/ai/references/review-checklist.md` | Single ordered checklist; the spine of a review pass. |
| `docs/theming-guide/ai/references/grep-recipes.md` | `rg` recipes per anti-pattern. |
| `docs/theming-guide/ai/references/severity-rubric.md` | `block` / `warn` / `nit` definitions + finding output format. |
| `.claude/skills/brand/SKILL.md` | Slim skill entry point. Points to the docs paths above; carries no rule content of its own. |
| `.claude/skills/aesthetic/SKILL.md` | Only the brand pointer at the top — keep delegation in sync if scope changes. |
| `.claude/skills/ui-styling/SKILL.md` | Only the brand pointer at the top. |
| `.claude/skills/frontend-development/SKILL.md` | Only the brand pointer at the top. |

## Workflow

1. **Read the user's instruction.** Classify it:
   - **Add a rule** → which reference file does it belong in? (substitution, inline-style anti-pattern, accessibility rule, etc.) Pick exactly one.
   - **Change an existing rule** → find the reference file that owns it; edit there.
   - **Remove a rule** → confirm with the user it's no longer needed; delete from the reference file AND remove the `--8<--` snippet from `THEMING-GUIDE.md` if the whole reference file is going away.
   - **Add a new reference file** → create under `theming-guide/ai/references/`, append a row to the reference map in `theming-guide/ai/index.md`, append a `--8<-- "theming-guide/ai/references/<name>.md"` snippet block at the end of the `## References` section in `THEMING-GUIDE.md`, append a bullet to the SKILL.md "References (loaded on demand)" list.
   - **Change scope** (a frontend tree joins/leaves) → edit `scope.md` AND the SKILL.md description AND the `When To Use` section.
   - **New mandatory component** → add to `scope.md`, `component-substitutions.md`, AND `THEMING-GUIDE.md` §"Component Patterns".

2. **Edit the docs first** (always). The docs are the single source of truth — the skill points to them. If a rule moves between reference files, update both ends in one edit batch.

3. **Sync the skill** (`.claude/skills/brand/SKILL.md`) — keep it slim:
   - Skill stays ≤ 80 lines.
   - Description stays ≤ 200 chars (run `awk '/^description:/ { sub(/^description: /, ""); print length }' .claude/skills/brand/SKILL.md` to check).
   - Don't paste rule content into the skill — only update the bullet list of references and the "When To Use" / scope sentences if scope changed.

4. **Sync sibling skills** (`aesthetic`, `ui-styling`, `frontend-development`) — only the **brand pointer** at the top of each SKILL.md. Don't bloat — just ensure each delegates to `brand` for draftforge-specific theming.

5. **Verify backlinks both ways.** Every reference file must link back to a section of `THEMING-GUIDE.md` for the *why*. The canonical guide's `## Backlinks` section must list `brand` skill path and update command path. The skill must list the docs paths. Run:
   ```bash
   rg -l 'THEMING-GUIDE|brand/SKILL|theming-guide/ai' \
     docs/THEMING-GUIDE.md \
     docs/theming-guide \
     .claude/skills/brand \
     .claude/skills/aesthetic \
     .claude/skills/ui-styling \
     .claude/skills/frontend-development \
     .claude/commands/brand-update.md
   ```
   Every file in the management table should appear with at least one match.

6. **Verify line counts** (per skill-creator guidelines):
   ```bash
   wc -l .claude/skills/brand/SKILL.md \
         docs/theming-guide/ai/index.md \
         docs/theming-guide/ai/references/*.md
   ```
   Each file must be ≤ 150 lines. If a reference file overflows, split it (and add a row to the reference map + snippet block in `THEMING-GUIDE.md`).

7. **Verify snippet integrity.** The `## References` section in `THEMING-GUIDE.md` must contain one `--8<--` block per file under `theming-guide/ai/references/`:
   ```bash
   diff <(ls docs/theming-guide/ai/references/*.md | xargs -n1 basename | sort) \
        <(rg -o 'theming-guide/ai/references/[a-z-]+\.md' docs/THEMING-GUIDE.md | xargs -n1 basename | sort -u)
   ```
   No diff = good. Any mismatch = fix the snippet blocks.

8. **Confirm AI references stay hidden from nav.** The `nav:` block in `mkdocs.yml` must NOT list anything under `theming-guide/`. The canonical `THEMING-GUIDE.md` is listed as `Theming Guide: THEMING-GUIDE.md` under Development; the AI references are kept invisible:
   ```bash
   rg -n 'theming-guide/' mkdocs.yml
   # Expected: zero matches (the directory is intentionally not navigated)
   ```

9. **Smoke-render the docs** (only if mkdocs is available locally — skip otherwise):
   ```bash
   just docs::serve  # or mkdocs serve from repo root
   ```
   Verify the canonical THEMING-GUIDE page renders the included AI reference content under `## References` and that nothing under `theming-guide/` appears in the left navigation tree.

10. **Report changes.** End the pass with a one-paragraph summary listing: which reference file(s) changed, whether the skill description/scope changed, whether sibling skill pointers changed, and whether the canonical guide changed. Cite paths.

## What NOT To Do

- Do not paste rule content into `SKILL.md`. The skill's job is to point at the canonical refs.
- Do not edit individual frontend `.tsx` files in this pass — that's a normal review/edit, not a brand-rule update.
- Do not invent a new reference file when an existing one is the right home for the rule.
- Do not edit `frontend/app/app.css`, `frontend/tailwind.config.js`, or `frontend/app/components/ui/buttons/styles.ts` here — token/style-constant changes flow through a normal PR.
- Do not edit `frontend/app/components/ui/buttons/README.md` here — that's the folder convention, not the rule SSoT (but cross-reference it from `component-substitutions.md` if relevant).
- Do not add the AI references to `mkdocs.yml` `nav:` — they're intentionally hidden.

## Spec Reference

When uncertain about skill structure (length limits, frontmatter format, description quality, progressive disclosure), consult:
- `.claude/skills/skill-creator/SKILL.md` — skill structure rules.
- `.claude/skills/agent_skills_spec.md` — agent skills spec.
