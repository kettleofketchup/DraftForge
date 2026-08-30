# `~/components/ui/buttons/` — folder convention

This folder holds reusable, brand-aligned button components. As the
library grows, group buttons by **scope of use**, not by visual style.

## Folder structure

```
buttons/
├── README.md             ← this guide
├── index.ts              ← barrel re-export of EVERYTHING
├── styles.ts             ← shared style constants (brandGradient, buttonLift, …)
│
├── PrimaryButton.tsx     ← generic, shape-agnostic buttons live at the root
├── SecondaryButton.tsx
├── EditButton.tsx
├── …
│
├── icons/                ← icon-only variants of generic buttons
│   ├── index.ts
│   ├── EditIconButton.tsx
│   ├── ViewIconButton.tsx
│   └── …
│
└── <domain>/             ← domain-specific buttons (one folder per domain)
    ├── index.ts
    └── DomainXxxButton.tsx
```

## When to add a new file vs. a new folder

| Situation | Where it goes |
|---|---|
| Generic action button used across many domains (e.g. `<EditButton>`, `<NavButton>`) | Root of `buttons/` |
| Icon-only variant of a generic button | `buttons/icons/` |
| Button tied to a specific external platform / domain (Dotabuff, Steam, Discord) | `buttons/<domain>/` (e.g. `buttons/user/`) |
| Page-specific button only used in one feature | Co-locate in the feature folder, **not** in `buttons/` |

## Existing groups

- **Root** (`buttons/*.tsx`) — generic brand buttons (PrimaryButton, SecondaryButton, EditButton, NavButton, ConfirmButton, DestructiveButton, …)
- **`buttons/icons/`** — icon-only variants (EditIconButton, ViewIconButton, TrashIconButton, …). These all use `size="icon"` on the underlying shadcn `<Button>`.
- **`buttons/user/`** — buttons tied to a player profile / external player platform. DotabuffButton, DotabuffIconButton.

## Rules

1. **Always re-export through `buttons/index.ts`.** Consumers should be able to write `import { DotabuffButton } from '~/components/ui/buttons'` without knowing about subfolders.
2. **Prefer composition over duplication.** `DotabuffButton` wraps `SecondaryButton` with `asChild` — it doesn't reimplement the brand styling. New domain buttons should follow the same pattern (compose root brand buttons, don't re-create their styles).
3. **Use the THEMING-GUIDE's Button Selection Guide** (`docs/THEMING-GUIDE.md`) to pick the right base. Edit affordances → `EditButton`/`EditIconButton` (toxic gradient). Supporting/contextual actions → `SecondaryButton`. CTAs → `PrimaryButton`. Etc.
4. **Mobile defaults matter.** A button in dense card lists should default to `responsive` mode that collapses to icon-only at `< sm`. See `<DotabuffButton>` for the pattern (`responsive` prop, `false` to opt out).
5. **No Radix `<Tooltip>` on dense lists.** Use the native `title` attribute. Each Radix Tooltip pulls in TooltipTrigger + TooltipPortal + TooltipContent — multiplied by every visible card on a virtualized grid, this dominates render cost. Native title has zero React render cost.
6. **`asChild` for external links.** When the button is a link, take an `asChild` prop or compose `SecondaryButton asChild` so the rendered element can be `<a>`. Preserve `target="_blank"` + `rel="noopener noreferrer"`.

## Adding a new domain group

```bash
# 1. Create the folder + barrel
mkdir -p frontend/app/components/ui/buttons/<domain>
cat > frontend/app/components/ui/buttons/<domain>/index.ts <<'EOF'
export { FooButton } from './FooButton';
export type { FooButtonProps } from './FooButton';
EOF

# 2. Wire into the root barrel
# Add to frontend/app/components/ui/buttons/index.ts:
#   export { FooButton } from './<domain>';
#   export type { FooButtonProps } from './<domain>';
```

That's it. Existing imports keep working because everything funnels through the root barrel.

## Anti-patterns

- ❌ Buttons that re-implement `brandGradient` / `buttonLift` instead of composing `PrimaryButton`/`SecondaryButton`/etc.
- ❌ Buttons with hand-rolled hover transitions when `transform-gpu transition-transform duration-150 hover:scale-[1.02]` is the brand-standard hover.
- ❌ Domain-specific buttons in the root folder.
- ❌ Buttons that import from a feature folder back into `ui/buttons/` (introduces circular dependency).
