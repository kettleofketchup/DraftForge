# Brand Button System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Issue:** [#123 - Refactor: Consolidate button styling with brand gradient system](https://github.com/kettleofketchup/DraftForge/issues/123)

**Goal:** Establish a two-tier brand button system (primary gradient + secondary translucent) and migrate all hardcoded emerald buttons to use it.

**Architecture:** Add `brandSecondary` constant to `styles.ts`. Update `PrimaryButton` to default to brand gradient + 3D depth. Add `brand` color option to `SecondaryButton`. Migrate all 6 hardcoded emerald buttons + 1 unstyled submit button.

**Tech Stack:** React, TypeScript, TailwindCSS, shadcn/ui Button

---

### Task 1: Add `brandSecondary` to styles.ts

**Files:**
- Modify: `frontend/app/components/ui/buttons/styles.ts:6`

**Step 1: Add the brandSecondary constant**

After the existing `brandGradient` line (line 6), add:

```ts
// Brand secondary - supporting/contextual actions
export const brandSecondary = 'bg-violet-500/15 border border-violet-400/20 text-violet-200 hover:bg-violet-500/25';
```

**Step 2: Export from index.ts**

Modify `frontend/app/components/ui/buttons/index.ts` line 2 to include the new export:

```ts
export { brandGradient, brandSecondary, button3DBase, button3DDisabled, button3DVariants } from './styles';
```

**Step 3: Verify TypeScript compiles**

Run: `cd /home/kettle/git_repos/website/.worktrees/brand-buttons && npx tsc --noEmit --pretty 2>&1 | grep -E "brandSecondary|styles\.ts" | head -5`
Expected: No errors related to brandSecondary or styles.ts

**Step 4: Commit**

```bash
git add frontend/app/components/ui/buttons/styles.ts frontend/app/components/ui/buttons/index.ts
git commit -m "feat: add brandSecondary style constant (closes #123 partial)"
```

---

### Task 2: Update PrimaryButton to brand gradient + 3D default

**Files:**
- Modify: `frontend/app/components/ui/buttons/PrimaryButton.tsx`

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
  green: 'bg-green-700 hover:bg-green-600 text-white',
  blue: 'bg-blue-700 hover:bg-blue-600 text-white',
  yellow: 'bg-yellow-600 hover:bg-yellow-500 text-black',
};

const brandClasses = `${brandGradient} border-b-violet-700 shadow-violet-900/50 [&_svg]:text-white [&_svg]:fill-white [&_svg]:drop-shadow-[1px_1px_1px_rgba(0,0,0,0.5)]`;

const PrimaryButton = React.forwardRef<HTMLButtonElement, PrimaryButtonProps>(
  ({ color, className, children, depth = true, ...props }, ref) => {
    const isBrand = !color;
    return (
      <Button
        ref={ref}
        className={cn(
          isBrand && depth && button3DBase,
          isBrand && depth && button3DDisabled,
          isBrand ? brandClasses : colorClasses[color],
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

Key changes:
- Default (no `color`) now renders brand gradient + 3D depth
- `depth` prop (default true) controls 3D effects — only applies to brand variant
- Old `color` prop preserved for backward compatibility
- Brand variant includes SVG icon styling for white icons with drop shadow

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

Add `'brand'` to the `BorderColor` type and add the brand secondary classes to both maps.

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

4. Add brand entry to `bgColorClasses` (after lime):
```ts
brand: 'bg-violet-500/15 border border-violet-400/20 text-violet-200 hover:bg-violet-500/25',
```

5. When `color="brand"`, force `depth={false}` behavior — the brand secondary style is flat. Update the component logic so that brand color skips 3D classes. Replace the className in the Button:

```tsx
const SecondaryButton = React.forwardRef<
  HTMLButtonElement,
  SecondaryButtonProps
>(({ borderColor, color, className, children, depth = true, ...props }, ref) => {
  const isBrand = color === 'brand' || borderColor === 'brand';
  const useDepth = depth && !isBrand;
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

**Step 1: Replace hardcoded emerald with brand gradient**

Replace the className block (lines 32-38) with:

```tsx
className={cn(
  'rounded-full',
  'bg-gradient-to-r from-violet-500 to-blue-500 hover:from-violet-400 hover:to-blue-400 text-white',
  'shadow-lg shadow-violet-900/50 border-b-4 border-b-violet-700',
  'active:border-b-0 active:translate-y-1 transition-all duration-75',
  '[&_svg]:text-white',
  className
)}
```

Changes: `emerald-600` → brand gradient, `emerald-900/50` → `violet-900/50`, `emerald-800` → `violet-700`.

**Step 2: Commit**

```bash
git add frontend/app/components/ui/buttons/icons/PlusIconButton.tsx
git commit -m "refactor: PlusIconButton uses brand gradient instead of emerald"
```

---

### Task 5: Update EditIconButton to brand gradient

**Files:**
- Modify: `frontend/app/components/ui/buttons/icons/EditIconButton.tsx`

**Step 1: Replace hardcoded emerald with brand gradient**

Replace the className block (lines 35-41) with:

```tsx
className={cn(
  'rounded-full',
  'bg-gradient-to-r from-violet-500 to-blue-500 hover:from-violet-400 hover:to-blue-400 text-white',
  'shadow-lg shadow-violet-900/50 border-b-4 border-b-violet-700',
  'active:border-b-0 active:translate-y-1 transition-all duration-75',
  '[&_svg]:text-white',
  className
)}
```

Same pattern as PlusIconButton.

**Step 2: Commit**

```bash
git add frontend/app/components/ui/buttons/icons/EditIconButton.tsx
git commit -m "refactor: EditIconButton uses brand gradient instead of emerald"
```

---

### Task 6: Migrate tournament createModal trigger

**Files:**
- Modify: `frontend/app/components/tournament/create/createModal.tsx`

**Step 1: Replace import and button**

1. Replace the `Button` import (line 4):
```ts
import { PrimaryButton } from '~/components/ui/buttons';
```

Remove the unused `Button` import from `~/components/ui/button`.

2. Replace the trigger button (lines 40-53) with:
```tsx
<PrimaryButton
  size="lg"
  data-testid="tournament-create-button"
>
  <PlusCircleIcon className="text-white" />
  Create Tournament
</PrimaryButton>
```

The `PrimaryButton` now provides brand gradient + 3D depth by default, so no className overrides needed.

**Step 2: Commit**

```bash
git add frontend/app/components/tournament/create/createModal.tsx
git commit -m "refactor: tournament create trigger uses PrimaryButton"
```

---

### Task 7: Migrate team createModal trigger

**Files:**
- Modify: `frontend/app/components/team/teamCard/createModal.tsx`

**Step 1: Replace import and button**

1. Replace the `Button` import (line 5):
```ts
import { PrimaryButton } from '~/components/ui/buttons';
```

Remove the unused `Button` import from `~/components/ui/button`.

2. Replace the trigger button (lines 63-76) with:
```tsx
<PrimaryButton
  size="lg"
  onClick={() => setOpen(true)}
>
  <PlusCircleIcon size="lg" className="text-white p-2" />
  Create Team
</PrimaryButton>
```

**Step 2: Commit**

```bash
git add frontend/app/components/team/teamCard/createModal.tsx
git commit -m "refactor: team create trigger uses PrimaryButton"
```

---

### Task 8: Migrate user createModal trigger

**Files:**
- Modify: `frontend/app/components/user/userCard/createModal.tsx`

**Step 1: Replace import and button**

1. Replace the `Button` import (line 19):
```ts
import { PrimaryButton } from '~/components/ui/buttons';
```

Remove the unused `Button` import from `~/components/ui/button`. Keep `CancelButton, SubmitButton` import on line 20 as-is.

2. Replace the trigger button (lines 100-112) with:
```tsx
<PrimaryButton
  size="lg"
>
  <PlusCircleIcon className="text-white" />
  Create User
</PrimaryButton>
```

**Step 2: Commit**

```bash
git add frontend/app/components/user/userCard/createModal.tsx
git commit -m "refactor: user create trigger uses PrimaryButton"
```

---

### Task 9: Migrate game createGameModal trigger

**Files:**
- Modify: `frontend/app/components/game/create/createGameModal.tsx`

**Step 1: Replace import and button**

1. Replace the `Button` import (line 3):
```ts
import { PrimaryButton } from '~/components/ui/buttons';
```

Remove the unused `Button` import from `~/components/ui/button`.

2. Replace the trigger button (lines 37-49) with:
```tsx
<PrimaryButton
  size="lg"
  onClick={() => setOpen(true)}
>
  <PlusCircleIcon className="text-white" />
  Create Game
</PrimaryButton>
```

**Step 3: Commit**

```bash
git add frontend/app/components/game/create/createGameModal.tsx
git commit -m "refactor: game create trigger uses PrimaryButton"
```

---

### Task 10: Migrate tournament editForm submit button

**Files:**
- Modify: `frontend/app/components/tournament/create/editForm.tsx`

**Step 1: Add SubmitButton import**

Add to the imports (replace or supplement the `Button` import on line 10):
```ts
import { SubmitButton } from '~/components/ui/buttons';
```

Keep the `Button` import if it's still used elsewhere in the file (the Cancel button on line 404 uses it). Check: the Cancel button uses `Button variant="outline"` — that stays.

**Step 2: Replace submit button**

Replace lines 413-425:
```tsx
<Button
  type="submit"
  disabled={isSubmitting}
  data-testid="tournament-submit-button"
>
  {isSubmitting
    ? isEditing
      ? 'Saving...'
      : 'Creating...'
    : isEditing
      ? 'Save Changes'
      : 'Create Tournament'}
</Button>
```

With:
```tsx
<SubmitButton
  loading={isSubmitting}
  loadingText={isEditing ? 'Saving...' : 'Creating...'}
  data-testid="tournament-submit-button"
>
  {isEditing ? 'Save Changes' : 'Create Tournament'}
</SubmitButton>
```

`SubmitButton` already uses `button3DVariants.success` which applies the brand gradient + 3D.

**Step 3: Commit**

```bash
git add frontend/app/components/tournament/create/editForm.tsx
git commit -m "refactor: tournament editForm uses SubmitButton with brand styling"
```

---

### Task 11: Final TypeScript check and visual verification

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
- PlusIconButton instances: Show brand gradient (circular)
- EditIconButton instances: Show brand gradient (circular)
- Tournament edit form: Submit button shows brand gradient + 3D
- FormDialog submit buttons: Still show brand gradient (unchanged)

**Step 3: Run Playwright tests**

Run: `cd /home/kettle/git_repos/website/.worktrees/brand-buttons && just test::pw::headless`
Expected: All tests pass (button styling changes are visual-only, no functional changes).
