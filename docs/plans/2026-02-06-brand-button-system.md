# Brand Button System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Issue:** [#123 - Refactor: Consolidate button styling with brand gradient system](https://github.com/kettleofketchup/DraftForge/issues/123)

**Goal:** Establish a consistent brand style system (primary gradient, secondary translucent, error surfaces) and migrate ALL hardcoded/unstyled create/add/submit buttons to use it. Update the THEMING-GUIDE.md to document the full system.

**Architecture:** Add `brandSecondary`, `brandErrorBg`, `brandErrorCard` constants to `styles.ts`. Update `PrimaryButton` to default to brand gradient + 3D depth. Add `brand` color option to `SecondaryButton`. Migrate all hardcoded emerald buttons, plain create/add triggers, and unstyled submit buttons.

**Design Principles:**
- Dark UI, neon-accented, gaming-styled = **muted surfaces + bright accents**
- Error surfaces use deep wine/red tones, NOT bright red — blends with the violet theme
- Uses raw Tailwind colors (`red-900`, not semantic `--error`) for error surfaces intentionally — the semantic error token (`rose-500`) is for bright accents, not muted backgrounds
- All class composition MUST use `cn()` (tailwind-merge) — never template literal interpolation

**Tech Stack:** React, TypeScript, TailwindCSS, shadcn/ui Button

---

### Task 1: Add brand constants to styles.ts

**Files:**
- Modify: `frontend/app/components/ui/buttons/styles.ts:6`
- Modify: `frontend/app/components/ui/buttons/index.ts:2`

**Step 1: Add the new brand constants**

After the existing `brandGradient` line (line 6), add:

```ts
// Brand secondary - supporting/contextual actions
export const brandSecondary = 'bg-violet-500/15 border border-violet-400/20 text-violet-200 hover:bg-violet-500/25';

// Brand error surfaces - muted deep wine/red tones for error containers.
// Uses raw Tailwind colors (not semantic --error/--primary) because error surfaces
// need deep wine/muted tones, not the bright accent status colors.
export const brandErrorBg = 'bg-gradient-to-r from-red-900/40 to-violet-900/40 border border-red-500/20';
export const brandErrorCard = 'bg-red-900/60 border border-red-500/15';
```

**Step 2: Export from index.ts**

Modify `frontend/app/components/ui/buttons/index.ts` line 2 to include the new exports:

```ts
export { brandErrorBg, brandErrorCard, brandGradient, brandSecondary, button3DBase, button3DDisabled, button3DVariants } from './styles';
```

**Step 3: Verify TypeScript compiles**

Run: `cd /home/kettle/git_repos/website/.worktrees/brand-buttons && npx tsc --noEmit --pretty 2>&1 | grep -E "brandSecondary|brandError|styles\.ts" | head -5`
Expected: No errors related to new constants or styles.ts

**Step 4: Commit**

```bash
git add frontend/app/components/ui/buttons/styles.ts frontend/app/components/ui/buttons/index.ts
git commit -m "feat: add brandSecondary and brandError style constants (#123)"
```

---

### Task 2: Update PrimaryButton to brand gradient + 3D default

**Files:**
- Modify: `frontend/app/components/ui/buttons/PrimaryButton.tsx`

**Note:** This changes the default `<PrimaryButton>` (no `color` prop) from plain shadcn styling to brand gradient + 3D. Existing consumer `randomTeamsModal.tsx` uses `<PrimaryButton>` without `color` — it will gain the brand gradient, which is the desired behavior (it's a primary create action).

**Step 1: Rewrite PrimaryButton**

Replace the entire file content with:

```tsx
import * as React from 'react';
import { Button } from '~/components/ui/button';
import { cn } from '~/lib/utils';
import { brandGradient, button3DBase, button3DDisabled } from './styles';

export type PrimaryButtonColor = 'green' | 'blue' | 'yellow';

export interface PrimaryButtonProps
  extends Omit<React.ComponentProps<typeof Button>, 'variant'> {
  /** Color theme for the button (omit for brand gradient) */
  color?: PrimaryButtonColor;
  /** Whether to apply 3D depth effects (default: true) */
  depth?: boolean;
}

const colorClasses: Record<PrimaryButtonColor, string> = {
  green: 'bg-green-700 hover:bg-green-600 text-white border-b-green-900 shadow-green-900/50',
  blue: 'bg-blue-700 hover:bg-blue-600 text-white border-b-blue-900 shadow-blue-900/50',
  yellow: 'bg-yellow-600 hover:bg-yellow-500 text-black border-b-yellow-800 shadow-yellow-900/50',
};

const brandExtras = 'border-b-violet-700 shadow-violet-900/50 [&_svg]:text-white [&_svg]:fill-white [&_svg]:drop-shadow-[1px_1px_1px_rgba(0,0,0,0.5)]';

const PrimaryButton = React.forwardRef<HTMLButtonElement, PrimaryButtonProps>(
  ({ color, className, children, depth = true, ...props }, ref) => {
    const isBrand = !color;
    return (
      <Button
        ref={ref}
        className={cn(
          depth && button3DBase,
          depth && button3DDisabled,
          isBrand ? [brandGradient, brandExtras] : colorClasses[color],
          className
        )}
        {...props}
      >
        {children}
      </Button>
    );
  }
);

PrimaryButton.displayName = 'PrimaryButton';

export { PrimaryButton };
```

Key changes from original plan (review fixes):
- `depth` applies to ALL variants (not just brand) — consistent with SecondaryButton behavior
- `colorClasses` now includes border-b and shadow colors for proper 3D with color variants
- `brandGradient` and `brandExtras` are passed separately to `cn()` (not pre-composed via template literal) for proper tailwind-merge deduplication

**Step 2: Verify TypeScript compiles**

Run: `cd /home/kettle/git_repos/website/.worktrees/brand-buttons && npx tsc --noEmit --pretty 2>&1 | grep "PrimaryButton" | head -5`
Expected: No new errors related to PrimaryButton

**Step 3: Commit**

```bash
git add frontend/app/components/ui/buttons/PrimaryButton.tsx
git commit -m "feat: PrimaryButton defaults to brand gradient with 3D depth"
```

---

### Task 3: Add `brand` color option to SecondaryButton

**Files:**
- Modify: `frontend/app/components/ui/buttons/SecondaryButton.tsx`

**Step 1: Update SecondaryButton to support brand color**

In `SecondaryButton.tsx`, make these changes:

1. Add import for `brandSecondary`:
```ts
import { brandSecondary, button3DBase, button3DDisabled } from './styles';
```

2. Add `'brand'` to the `BorderColor` type (line 6):
```ts
export type BorderColor = 'green' | 'blue' | 'purple' | 'orange' | 'red' | 'sky' | 'cyan' | 'lime' | 'brand';
```

3. Add brand entry to `borderColorClasses` (after lime):
```ts
brand: 'border border-violet-400/20',
```

4. Add brand entry to `bgColorClasses` using the constant (after lime):
```ts
brand: brandSecondary,
```

5. Update the component to use `??` smart default for depth — brand defaults to flat, but caller can explicitly override:

```tsx
const SecondaryButton = React.forwardRef<
  HTMLButtonElement,
  SecondaryButtonProps
>(({ borderColor, color, className, children, depth, ...props }, ref) => {
  const isBrand = color === 'brand' || borderColor === 'brand';
  const useDepth = depth ?? !isBrand;
  return (
    <Button
      ref={ref}
      variant="secondary"
      className={cn(
        useDepth && button3DBase,
        useDepth && button3DDisabled,
        useDepth && '[&_svg]:text-white [&_svg]:drop-shadow-[1px_1px_1px_rgba(0,0,0,0.5)]',
        borderColor && borderColorClasses[borderColor],
        color && bgColorClasses[color],
        className
      )}
      {...props}
    >
      {children}
    </Button>
  );
});
```

Key change from original plan: `depth` defaults to `undefined` in destructure, `depth ?? !isBrand` applies smart default. Brand = flat by default but `<SecondaryButton color="brand" depth>` explicitly opts into 3D. Non-brand = 3D by default (preserves current behavior).

**Step 2: Verify TypeScript compiles**

Run: `cd /home/kettle/git_repos/website/.worktrees/brand-buttons && npx tsc --noEmit --pretty 2>&1 | grep "SecondaryButton" | head -5`
Expected: No new errors

**Step 3: Commit**

```bash
git add frontend/app/components/ui/buttons/SecondaryButton.tsx
git commit -m "feat: SecondaryButton supports brand color (translucent violet)"
```

---

### Task 4: Update PlusIconButton to brand gradient

**Files:**
- Modify: `frontend/app/components/ui/buttons/icons/PlusIconButton.tsx`

**Step 1: Add import and replace hardcoded emerald**

Add import:
```ts
import { brandGradient, button3DBase } from '../styles';
```

Replace the className block (lines 32-38) with:

```tsx
className={cn(
  'rounded-full',
  brandGradient,
  button3DBase,
  'border-b-violet-700 shadow-violet-900/50',
  '[&_svg]:text-white',
  className
)}
```

Key change from original plan: Uses `brandGradient` and `button3DBase` constants instead of duplicating the strings inline. Single source of truth.

**Step 2: Commit**

```bash
git add frontend/app/components/ui/buttons/icons/PlusIconButton.tsx
git commit -m "refactor: PlusIconButton uses brand gradient constant instead of emerald"
```

---

### Task 5: Update EditIconButton to brand gradient

**Files:**
- Modify: `frontend/app/components/ui/buttons/icons/EditIconButton.tsx`

**Step 1: Add import and replace hardcoded emerald**

Add import:
```ts
import { brandGradient, button3DBase } from '../styles';
```

Replace the className block (lines 35-41) with:

```tsx
className={cn(
  'rounded-full',
  brandGradient,
  button3DBase,
  'border-b-violet-700 shadow-violet-900/50',
  '[&_svg]:text-white',
  className
)}
```

Same pattern as PlusIconButton.

**Step 2: Commit**

```bash
git add frontend/app/components/ui/buttons/icons/EditIconButton.tsx
git commit -m "refactor: EditIconButton uses brand gradient constant instead of emerald"
```

---

### Task 6: Migrate emerald create modal triggers (4 files)

**Files:**
- Modify: `frontend/app/components/tournament/create/createModal.tsx`
- Modify: `frontend/app/components/team/teamCard/createModal.tsx`
- Modify: `frontend/app/components/user/userCard/createModal.tsx`
- Modify: `frontend/app/components/game/create/createGameModal.tsx`

For each file:

1. Replace `import { Button } from '~/components/ui/button'` with `import { PrimaryButton } from '~/components/ui/buttons'` (remove unused Button import)

2. Replace the emerald `<Button>` with `<PrimaryButton>`:

**tournament/create/createModal.tsx** (lines 40-53):
```tsx
<PrimaryButton
  size="lg"
  data-testid="tournament-create-button"
>
  <PlusCircleIcon className="text-white" />
  Create Tournament
</PrimaryButton>
```

**team/teamCard/createModal.tsx** (lines 63-76):
```tsx
<PrimaryButton
  size="lg"
  onClick={() => setOpen(true)}
>
  <PlusCircleIcon size="lg" className="text-white p-2" />
  Create Team
</PrimaryButton>
```

**user/userCard/createModal.tsx** (lines 100-112):
Replace `import { Button } from '~/components/ui/button'` with `import { PrimaryButton } from '~/components/ui/buttons'`. Keep the `CancelButton, SubmitButton` import on line 20.
```tsx
<PrimaryButton
  size="lg"
>
  <PlusCircleIcon className="text-white" />
  Create User
</PrimaryButton>
```

**game/create/createGameModal.tsx** (lines 37-49):
```tsx
<PrimaryButton
  size="lg"
  onClick={() => setOpen(true)}
>
  <PlusCircleIcon className="text-white" />
  Create Game
</PrimaryButton>
```

**Commit:**

```bash
git add frontend/app/components/tournament/create/createModal.tsx frontend/app/components/team/teamCard/createModal.tsx frontend/app/components/user/userCard/createModal.tsx frontend/app/components/game/create/createGameModal.tsx
git commit -m "refactor: migrate emerald create modal triggers to PrimaryButton (#123)"
```

---

### Task 7: Migrate plain create/add trigger buttons (6 files)

**Files (found by migration review — missed in original plan):**
- Modify: `frontend/app/routes/organizations.tsx` (~line 130)
- Modify: `frontend/app/routes/organization.tsx` (~lines 221, 254)
- Modify: `frontend/app/routes/leagues.tsx` (~line 173)
- Modify: `frontend/app/pages/tournament/tabs/PlayersTab.tsx` (~line 72)
- Modify: `frontend/app/components/league/tabs/UsersTab.tsx` (~line 63)

These are plain `<Button>` create/add triggers with no styling. Replace with `<PrimaryButton>`:

For each file:
1. Add `import { PrimaryButton } from '~/components/ui/buttons'`
2. Replace `<Button onClick={...}>` with `<PrimaryButton onClick={...}>`
3. Remove unused `Button` import if no other usage remains (check each file)

**organizations.tsx** (line 130):
```tsx
<PrimaryButton onClick={() => setCreateModalOpen(true)}>
  <Plus className="w-4 h-4 mr-2" />
  Create Organization
</PrimaryButton>
```

**organization.tsx** (line 221 — Create League):
```tsx
<PrimaryButton onClick={() => setCreateLeagueOpen(true)}>
  <Plus className="w-4 h-4 mr-2" />
  Create League
</PrimaryButton>
```

**organization.tsx** (line 254 — Add Member): This is an "Add" action within a tab, keep as `size="sm"`:
```tsx
<PrimaryButton size="sm" onClick={() => setShowAddUser(true)} data-testid="org-add-member-btn">
  <Plus className="w-4 h-4 mr-2" />
  Add Member
</PrimaryButton>
```

**leagues.tsx** (line 173):
```tsx
<PrimaryButton onClick={() => setCreateModalOpen(true)}>
  <Plus className="w-4 h-4 mr-2" />
  Create League
</PrimaryButton>
```

**PlayersTab.tsx** (line 72):
```tsx
<PrimaryButton onClick={() => setShowAddUser(true)} data-testid="tournamentAddPlayerBtn">
  <Plus className="w-4 h-4 mr-2" />
  Add Player
</PrimaryButton>
```

**league/tabs/UsersTab.tsx** (line 63):
```tsx
<PrimaryButton size="sm" onClick={() => setShowAddUser(true)} data-testid="league-add-member-btn">
  <Plus className="w-4 h-4 mr-2" />
  Add Member
</PrimaryButton>
```

**Commit:**

```bash
git add frontend/app/routes/organizations.tsx frontend/app/routes/organization.tsx frontend/app/routes/leagues.tsx frontend/app/pages/tournament/tabs/PlayersTab.tsx frontend/app/components/league/tabs/UsersTab.tsx
git commit -m "refactor: migrate plain create/add triggers to PrimaryButton (#123)"
```

---

### Task 8: Migrate unstyled submit buttons (2 files)

**Files:**
- Modify: `frontend/app/components/tournament/create/editForm.tsx`
- Modify: `frontend/app/pages/user/EditProfileModal.tsx`

**editForm.tsx:**

1. Add import:
```ts
import { SubmitButton } from '~/components/ui/buttons';
```

2. Keep `Button` import (used by Cancel button on line 404).

3. Replace lines 413-425:
```tsx
<SubmitButton
  loading={isSubmitting}
  loadingText={isEditing ? 'Saving...' : 'Creating...'}
  data-testid="tournament-submit-button"
>
  {isEditing ? 'Save Changes' : 'Create Tournament'}
</SubmitButton>
```

**EditProfileModal.tsx:**

1. Add import:
```ts
import { SubmitButton } from '~/components/ui/buttons';
```

2. Keep `Button` import (used by Cancel button on line 212).

3. Replace line 219-221:
```tsx
<SubmitButton
  loading={form.formState.isSubmitting}
  loadingText="Saving..."
>
  Save Changes
</SubmitButton>
```

**Commit:**

```bash
git add frontend/app/components/tournament/create/editForm.tsx frontend/app/pages/user/EditProfileModal.tsx
git commit -m "refactor: migrate unstyled submit buttons to SubmitButton (#123)"
```

---

### Task 9: Fix SubmitButton JSDoc

**Files:**
- Modify: `frontend/app/components/ui/buttons/SubmitButton.tsx`

**Step 1: Update stale JSDoc**

On line 18, replace:
```ts
 * A submit button with green theme styling and 3D depth effects for form submissions.
```

With:
```ts
 * A submit button with brand gradient styling and 3D depth effects for form submissions.
```

**Commit:**

```bash
git add frontend/app/components/ui/buttons/SubmitButton.tsx
git commit -m "docs: fix stale SubmitButton JSDoc (green -> brand gradient)"
```

---

### Task 10: Migrate tournament hasErrors.tsx to brand error surfaces

**Files:**
- Modify: `frontend/app/pages/tournament/hasErrors.tsx`

**Step 1: Add imports**

Add at the top of the file:
```ts
import { brandErrorBg, brandErrorCard } from '~/components/ui/buttons';
import { cn } from '~/lib/utils';
```

**Step 2: Replace container styling using `cn()` (not template literals)**

On line 60, replace:
```tsx
<div className="flex flex-col items-start justify-center p-4 bg-red-950 rounded-lg shadow-md w-full mb-4">
```

With:
```tsx
<div className={cn('flex flex-col items-start justify-center p-4 rounded-lg shadow-md w-full mb-4', brandErrorBg)}>
```

**Step 3: Replace card styling using `cn()`**

On line 70, replace:
```tsx
<div className="bg-red-500/80 p-3 rounded-lg" key={user.pk}>
```

With:
```tsx
<div className={cn('p-3 rounded-lg', brandErrorCard)} key={user.pk}>
```

**Step 4: Commit**

```bash
git add frontend/app/pages/tournament/hasErrors.tsx
git commit -m "refactor: tournament hasErrors uses brand error surfaces instead of bright red"
```

---

### Task 11: Update THEMING-GUIDE.md

**Files:**
- Modify: `docs/THEMING-GUIDE.md`

**Context:** The theming guide is out of date and needs updating with Tailwind specifics. It doesn't document the brand button system, the 3D depth variants, the error surface palette, or the button selection guide. This task brings it current.

**Step 1: Update "Color Palette > Primary" section**

Replace the current Primary section (lines 15-26) with:

```markdown
### Primary (Brand) - Violet-to-Blue Gradient

| Token | Tailwind Classes | Usage |
|-------|-----------------|-------|
| `--primary` | `bg-primary` (violet-400 dark) | Base brand color: focus rings, links, badges |
| `brandGradient` | `bg-gradient-to-r from-violet-500 to-blue-500 hover:from-violet-400 hover:to-blue-400 text-white` | Primary CTA buttons |
| `brandSecondary` | `bg-violet-500/15 border border-violet-400/20 text-violet-200 hover:bg-violet-500/25` | Supporting/contextual actions |

Primary CTA buttons use the brand gradient via `<PrimaryButton>`, not flat `bg-primary`. The `--primary` CSS variable remains the base brand color for non-button contexts.

```tsx
// Primary CTA (brand gradient + 3D depth)
<PrimaryButton>Create Tournament</PrimaryButton>
<PrimaryButton depth={false}>Flat Variant</PrimaryButton>

// Secondary brand action (translucent violet, flat)
<SecondaryButton color="brand">Edit Settings</SecondaryButton>
```
```

**Step 2: Update "Status Colors" section**

Add error surface rows to the status colors table (after the existing Error row):

```markdown
| Error (text/badges) | rose-500 | `text-error`, `bg-destructive` | Inline errors, delete buttons |
| Error (surfaces) | red-900/violet-900 | `brandErrorBg` | Error containers — muted wine gradient |
| Error (cards) | red-900/60 | `brandErrorCard` | Error cards within containers |
```

Add a note:
```markdown
> **Error surfaces** use raw Tailwind colors (`red-900`, `violet-900`) instead of semantic `--error` tokens. This is intentional: error containers need deep wine/muted tones to maintain the "muted surfaces + bright accents" pattern. The semantic `rose-500` error token is for bright inline accents.
```

**Step 3: Add new "Brand Button System" section after "Gradient Utilities"**

```markdown
## Brand Button System

### Style Constants

All brand style constants are exported from `~/components/ui/buttons`:

| Constant | Tailwind Classes | Usage |
|----------|-----------------|-------|
| `brandGradient` | `bg-gradient-to-r from-violet-500 to-blue-500 hover:from-violet-400 hover:to-blue-400 text-white` | Primary CTA color |
| `brandSecondary` | `bg-violet-500/15 border border-violet-400/20 text-violet-200 hover:bg-violet-500/25` | Supporting actions |
| `brandErrorBg` | `bg-gradient-to-r from-red-900/40 to-violet-900/40 border border-red-500/20` | Error container surfaces |
| `brandErrorCard` | `bg-red-900/60 border border-red-500/15` | Error cards |

### 3D Depth Effects

Buttons support a `depth` prop for 3D press effects:

```tsx
// 3D button (default for PrimaryButton)
<PrimaryButton>Create</PrimaryButton>

// Flat button
<PrimaryButton depth={false}>Create</PrimaryButton>
```

The 3D system uses `button3DBase` (shadow, border-b-4, active press) and `button3DDisabled` (muted disabled state).

### Button Selection Guide

| Context | Component | Visual |
|---------|-----------|--------|
| Page-level CTA (not in a form) | `<PrimaryButton>` | Brand gradient + 3D |
| Form submission | `<SubmitButton>` | Brand gradient + 3D |
| Dialog confirmation | `<ConfirmButton variant="success">` | Brand gradient + 3D |
| Destructive dialog action | `<ConfirmButton variant="destructive">` | Red + 3D |
| Warning dialog action | `<ConfirmButton variant="warning">` | Orange + 3D |
| Supporting/contextual action | `<SecondaryButton color="brand">` | Translucent violet (flat) |
| Cancel/dismiss | `<CancelButton>` | Outline |
| Destructive page action | `<DestructiveButton>` | Red + 3D |

> `PrimaryButton`, `SubmitButton`, and `ConfirmButton variant="success"` share the brand gradient visual. Choose based on HTML semantics and context, not appearance.
```

**Step 4: Update "Component Patterns > Buttons" section**

Replace the existing Buttons section with:

```markdown
### Buttons

```tsx
// Primary CTA (brand gradient + 3D depth)
<PrimaryButton>Create Tournament</PrimaryButton>
<PrimaryButton size="lg">Large CTA</PrimaryButton>

// Form submission
<SubmitButton loading={isSubmitting}>Save Changes</SubmitButton>

// Dialog confirmation
<ConfirmButton variant="success">Approve</ConfirmButton>
<ConfirmButton variant="destructive">Delete</ConfirmButton>

// Secondary with brand styling (translucent violet, flat)
<SecondaryButton color="brand">Settings</SecondaryButton>

// Secondary with colored background + 3D
<SecondaryButton color="cyan" depth>Colored Action</SecondaryButton>

// Plain shadcn variants (still available)
<Button variant="outline">Outline</Button>
<Button variant="ghost">Ghost</Button>
<Button variant="destructive">Delete</Button>
```
```

**Step 5: Update "Quick Reference > Most Used Classes"**

Add to the quick reference under a new "Brand tokens" section:

```tsx
// Brand tokens (import from ~/components/ui/buttons)
brandGradient          // Primary CTA gradient (violet-to-blue)
brandSecondary         // Translucent violet for secondary actions
brandErrorBg           // Muted wine error container
brandErrorCard         // Dark red error card
```

**Step 6: Commit**

```bash
git add docs/THEMING-GUIDE.md
git commit -m "docs: update THEMING-GUIDE with brand button system and Tailwind specifics (#123)"
```

---

### Task 12: Final TypeScript check and visual verification

**Step 1: Run full TypeScript check**

Run: `cd /home/kettle/git_repos/website/.worktrees/brand-buttons && npx tsc --noEmit --pretty 2>&1 | tail -20`
Expected: No new errors (pre-existing errors in bracketAPI, editForm, heroDraftStore, dotaconstants, playwright configs are known and acceptable).

**Step 2: Start dev environment and visually verify**

Run: `cd /home/kettle/git_repos/website/.worktrees/brand-buttons && just dev::debug`

Verify in browser:
- Tournament page: Create Tournament button shows brand gradient + 3D
- Team page: Create Team button shows brand gradient + 3D
- User page: Create User button shows brand gradient + 3D
- Game page: Create Game button shows brand gradient + 3D
- Organizations page: Create Organization button shows brand gradient + 3D
- Organization page: Create League + Add Member buttons show brand gradient + 3D
- Leagues page: Create League button shows brand gradient + 3D
- Players tab: Add Player button shows brand gradient + 3D
- League Users tab: Add Member button shows brand gradient + 3D
- PlusIconButton instances: Show brand gradient (circular)
- EditIconButton instances: Show brand gradient (circular)
- Tournament edit form: Submit button shows brand gradient + 3D
- Edit profile modal: Submit button shows brand gradient + 3D
- FormDialog submit buttons: Still show brand gradient (unchanged)
- Tournament hasErrors section: Muted wine-to-violet gradient container, deep red cards (not bright)
- Random teams modal: PrimaryButton shows brand gradient + 3D (side effect — intentional)

**Step 3: Run Playwright tests**

Run: `cd /home/kettle/git_repos/website/.worktrees/brand-buttons && just test::pw::headless`
Expected: All tests pass (button styling changes are visual-only, no functional changes).
