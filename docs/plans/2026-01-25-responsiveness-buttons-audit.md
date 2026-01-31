# Frontend Button Patterns Audit

**Date**: 2026-01-25
**Purpose**: Comprehensive audit of button patterns in the DraftForge frontend
**Scope**: `/home/kettle/git_repos/website/.worktrees/responsiveness/frontend/app/`

## Executive Summary

The codebase contains **130+ Button usages** across 50+ files with significant inconsistencies in styling, loading states, and accessibility patterns. Most buttons use the shadcn/ui Button primitive directly with inline styling rather than purpose-built custom components.

### Key Findings

1. **No component abstraction**: Direct Button usage everywhere instead of wrapped custom components
2. **Inconsistent loading states**: Some buttons manually add Loader2, others just show "Submitting..."
3. **Inconsistent destructive styling**: Mix of `variant="destructive"`, manual `bg-red-*` classes
4. **Inconsistent icon button sizing**: Various approaches to icon-only buttons
5. **Motion wrapper in base Button**: The Button component wraps in `motion.div` which affects layout

---

## 1. Current Button Patterns Found

### 1.1 Submit/Confirm Buttons

**Purpose**: Form submissions, confirmations, primary actions

| File | Current Implementation | Issues |
|------|----------------------|--------|
| `CreateOrganizationModal.tsx:150` | `<Button type="submit" disabled={isSubmitting}>` | No loading spinner, text changes to "Creating..." |
| `CreateLeagueModal.tsx:159` | `<Button type="submit" disabled={isSubmitting}>` | Same pattern - inconsistent with modals that use spinners |
| `TournamentEditForm.tsx:399` | `<Button type="submit" disabled={isSubmitting}>` | Shows "Saving..." or "Creating..." |
| `profile.tsx:144` | `<Button type="submit">Submit</Button>` | No loading state at all |
| `AutoAssignModal.tsx:227` | Uses `<Loader2>` spinner + "Applying..." | Good pattern but not abstracted |
| `HeroDraftModal.tsx:308-361` | `<Button onClick={handleReady} disabled={isSubmitting}>` | Shows "Submitting..." text, no spinner |

**Current Variations**:
```tsx
// Pattern 1: Text only change
<Button type="submit" disabled={isSubmitting}>
  {isSubmitting ? 'Creating...' : 'Create'}
</Button>

// Pattern 2: Loader + text
<Button onClick={applyAssignments} disabled={isApplying}>
  {isApplying ? (
    <>
      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
      Applying...
    </>
  ) : (
    <>
      <Wand2 className="h-4 w-4 mr-2" />
      Apply {result?.assignments.length || 0} Assignments
    </>
  )}
</Button>

// Pattern 3: No loading state
<Button type="submit">Submit</Button>
```

### 1.2 Cancel Buttons

**Purpose**: Close modals, cancel forms, secondary dismissal actions

| File | Current Implementation | Issues |
|------|----------------------|--------|
| `CreateOrganizationModal.tsx:142` | `<Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>` | Consistent pattern |
| `TournamentEditForm.tsx:390` | `<DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>` | Uses DialogClose wrapper |
| `draftStyleModal.tsx:319` | `<Button variant="outline">Cancel</Button>` | DialogTrigger asChild pattern |
| `userCard/editModal.tsx:102` | `<Button variant="outline">Cancel</Button>` | Standard pattern |
| `userCard/createModal.tsx:173` | `<Button className="justify-right">Cancel</Button>` | Missing variant="outline"! |

**Inconsistency**: Most use `variant="outline"` but some miss it entirely.

### 1.3 Delete/Destructive Buttons

**Purpose**: Delete items, remove users, destructive actions

| File | Current Implementation | Styling |
|------|----------------------|---------|
| `reusable/deleteButton.tsx:47` | `variant="outline"` + `className="bg-red-950 hover:bg-red-600 text-white"` | Custom red |
| `tournament/card/deleteButton.tsx:71` | `variant="outline"` + `className="bg-red-950 hover:bg-red-600 text-white"` | Identical |
| `game/gameCard/deleteButton.tsx:52` | `variant="outline"` + `className="bg-red-950 hover:bg-red-600 text-white"` | Identical |
| `user/userCard/deleteButton.tsx:81` | `variant="default"` + `className="bg-red-950 hover:bg-red-600 text-white"` | Different variant! |
| `playerRemoveButton.tsx:107` | `variant="outline"` + `className="bg-red-950 hover:bg-red-600 text-white"` | Standard |
| `BracketToolbar.tsx:107` | `variant="destructive"` | Uses built-in destructive |
| `navbar/login.tsx:142` | `variant={'destructive'}` | Uses built-in destructive |
| `HeroDraftModal.tsx:509` | `variant="destructive"` | Uses built-in destructive |
| `initDraftDialog.tsx:84` | `variant={'destructive'}` | Uses built-in destructive |

**Major Inconsistency**:
- Some use `variant="destructive"` (shadcn built-in)
- Others override with manual `bg-red-950 hover:bg-red-600` classes
- Different base variants (`outline` vs `default`) with same visual intent

### 1.4 Admin-Only Buttons

**Purpose**: Indicate admin-required actions, show permission state

| File | Current Implementation |
|------|----------------------|
| `reusable/adminButton.tsx` | Full component with Tooltip, motion animations |
| `initDraftDialog.tsx:62` | Uses `<AdminOnlyButton tooltipTxt="..."/>` |
| `choosePlayerButtons.tsx:95` | Uses `<AdminOnlyButton buttonTxt={...}/>` |
| `addPlayerModal.tsx:60` | Uses `<AdminOnlyButton buttonTxt="" tooltipTxt="..."/>` |

**Current AdminOnlyButton Implementation**:
```tsx
<Button className="btn btn-danger bg-red-900 text-white">
  <UserLock className="mr-2" />
  {buttonTxt}
</Button>
```

**Issues**:
- Uses legacy DaisyUI classes (`btn btn-danger`) mixed with Tailwind
- Wraps with motion.div that already exists in Button (double animation)
- Red coloring doesn't indicate "admin required" - looks like destructive action

### 1.5 Icon Buttons

**Purpose**: Compact buttons with only icons (navigation, toggles)

| File | Current Implementation | Size |
|------|----------------------|------|
| `prevButton.tsx:19` | `<Button className="bg-sky-900" size="icon">` | `size="icon"` |
| `nextButton.tsx:20` | `<Button className="bg-sky-900" size="icon">` | `size="icon"` |
| `addButton.tsx:30` | `<Button size="icon" variant="outline">` | `size="icon"` |
| `deleteButton.tsx:47` | `<Button variant="outline" size="sm">` | `size="sm"` not icon! |
| `zoom-slider.tsx:36-65` | `<Button variant="ghost" size="icon">` | Correct pattern |
| `HeroDraftModal.tsx:474-508` | `<Button variant="secondary" size="icon">` | Correct pattern |

**Inconsistency**: Delete buttons use `size="sm"` with icon content, not `size="icon"`

### 1.6 Navigation/Action Buttons

**Purpose**: Navigate, filter, view items

| File | Current Implementation |
|------|----------------------|
| `TournamentFilterBar.tsx:77` | `<Button variant="outline" size="sm">Filter</Button>` |
| `TournamentFilterBar.tsx:86` | `<Button variant="ghost" size="sm">Clear filters</Button>` |
| `TournamentCard.tsx:253` | `<Button variant={'secondary'} className="w-20">View</Button>` |
| `TournamentCard.tsx:266` | `<Button className="w-20 ml-0 bg-purple-900 text-white">Edit</Button>` |
| `LeaderboardPage.tsx:64-79` | `<Button variant="outline" size="sm">Previous/Next</Button>` |

**Inconsistency**: Edit button uses manual `bg-purple-900` instead of a variant

### 1.7 Loading State Buttons

**Purpose**: Show async operation in progress

**Current Patterns Found**:

```tsx
// Pattern A: Inline Loader2 + text (best pattern seen)
<Button disabled={isApplying}>
  {isApplying ? (
    <>
      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
      Applying...
    </>
  ) : 'Apply'}
</Button>

// Pattern B: Text-only change
<Button disabled={isSubmitting}>
  {isSubmitting ? 'Saving...' : 'Save'}
</Button>

// Pattern C: No loading indication
<Button onClick={handleSave}>Save</Button>
```

### 1.8 Home Page CTA Buttons

**Purpose**: Marketing/landing page call-to-action

| Location | Current Implementation |
|----------|----------------------|
| `home.tsx:193` | `<Button size="lg" className="!text-black" asChild>` |
| `home.tsx:199` | `<Button size="lg" variant="outline" className="shadow-md border-2 border-emerald-500 text-emerald-400 hover:bg-emerald-500/20">` |
| `home.tsx:296` | Same pattern |

**Issues**: Heavy inline styling for branded CTAs instead of branded variants

---

## 2. Inconsistencies Identified

### 2.1 Styling Inconsistencies

| Issue | Examples | Impact |
|-------|----------|--------|
| **Destructive colors** | `variant="destructive"` vs `bg-red-950` vs `bg-red-900` | Visual inconsistency for delete actions |
| **Icon button sizing** | `size="icon"` vs `size="sm"` with icon | Touch target inconsistency |
| **Cancel button variants** | `variant="outline"` vs no variant | Visual hierarchy broken |
| **Edit button colors** | `bg-purple-900` custom vs no standard | No recognizable "edit" pattern |
| **Legacy DaisyUI classes** | `btn btn-danger` mixed with Tailwind | Technical debt |

### 2.2 Behavioral Inconsistencies

| Issue | Examples | Impact |
|-------|----------|--------|
| **Loading states** | Spinner vs text-only vs none | User uncertainty about action state |
| **Disabled logic** | Some check `isSubmitting`, others don't | Double-submit bugs possible |
| **Motion animation** | Base Button has motion.div, AdminOnlyButton adds another | Double animation |

### 2.3 Accessibility Inconsistencies

| Issue | Examples | Impact |
|-------|----------|--------|
| **aria-label on icon buttons** | Some have it, some don't | Screen reader issues |
| **Tooltip wrapping** | Inconsistent TooltipProvider placement | Some tooltips may not work |

---

## 3. Recommended Custom Components

### 3.1 SubmitButton

**Purpose**: Form submissions with consistent loading state

```tsx
// components/custom/submit-button.tsx
import { Loader2 } from "lucide-react";
import { Button, type ButtonProps } from "~/components/ui/button";

interface SubmitButtonProps extends Omit<ButtonProps, "type"> {
  isLoading?: boolean;
  loadingText?: string;
}

export function SubmitButton({
  children,
  isLoading,
  loadingText,
  disabled,
  ...props
}: SubmitButtonProps) {
  return (
    <Button type="submit" disabled={disabled || isLoading} {...props}>
      {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
      {isLoading ? (loadingText ?? "Saving...") : children}
    </Button>
  );
}

// Usage:
<SubmitButton isLoading={isSubmitting}>Create Tournament</SubmitButton>
<SubmitButton isLoading={isSubmitting} loadingText="Creating...">Create</SubmitButton>
```

### 3.2 CancelButton

**Purpose**: Consistent cancel/close actions

```tsx
// components/custom/cancel-button.tsx
import { Button, type ButtonProps } from "~/components/ui/button";

interface CancelButtonProps extends ButtonProps {
  onClick?: () => void;
}

export function CancelButton({
  children = "Cancel",
  onClick,
  disabled,
  ...props
}: CancelButtonProps) {
  return (
    <Button type="button" variant="outline" onClick={onClick} disabled={disabled} {...props}>
      {children}
    </Button>
  );
}

// Usage:
<CancelButton onClick={() => onOpenChange(false)} />
<CancelButton disabled={isSubmitting}>Cancel</CancelButton>
```

### 3.3 DestructiveButton

**Purpose**: Delete, remove, and other destructive actions

```tsx
// components/custom/destructive-button.tsx
import { Loader2, Trash2 } from "lucide-react";
import { Button, type ButtonProps } from "~/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "~/components/ui/tooltip";

interface DestructiveButtonProps extends Omit<ButtonProps, "variant"> {
  isLoading?: boolean;
  tooltip?: string;
  iconOnly?: boolean;
}

export function DestructiveButton({
  children,
  isLoading,
  tooltip,
  iconOnly = false,
  disabled,
  ...props
}: DestructiveButtonProps) {
  const button = (
    <Button
      variant="destructive"
      size={iconOnly ? "icon" : "default"}
      disabled={disabled || isLoading}
      {...props}
    >
      {isLoading ? (
        <Loader2 className="h-4 w-4 animate-spin" />
      ) : iconOnly ? (
        <Trash2 className="h-4 w-4" />
      ) : (
        children
      )}
    </Button>
  );

  if (tooltip) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>{button}</TooltipTrigger>
        <TooltipContent>{tooltip}</TooltipContent>
      </Tooltip>
    );
  }

  return button;
}

// Usage:
<DestructiveButton iconOnly tooltip="Delete tournament" onClick={handleDelete} />
<DestructiveButton isLoading={isDeleting}>Delete</DestructiveButton>
```

### 3.4 IconButton

**Purpose**: Consistent icon-only buttons with proper sizing and accessibility

```tsx
// components/custom/icon-button.tsx
import { Button, type ButtonProps } from "~/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "~/components/ui/tooltip";

interface IconButtonProps extends Omit<ButtonProps, "size" | "children"> {
  icon: React.ReactNode;
  label: string; // Required for accessibility
  tooltip?: string;
}

export function IconButton({
  icon,
  label,
  tooltip,
  variant = "outline",
  ...props
}: IconButtonProps) {
  const button = (
    <Button size="icon" variant={variant} aria-label={label} {...props}>
      {icon}
    </Button>
  );

  if (tooltip) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>{button}</TooltipTrigger>
        <TooltipContent>{tooltip}</TooltipContent>
      </Tooltip>
    );
  }

  return button;
}

// Usage:
<IconButton
  icon={<ChevronsLeft className="h-4 w-4" />}
  label="Previous round"
  tooltip="Go to the previous draft round"
  onClick={goToPrevRound}
/>
```

### 3.5 LoadingButton

**Purpose**: Generic button with loading state

```tsx
// components/custom/loading-button.tsx
import { Loader2 } from "lucide-react";
import { Button, type ButtonProps } from "~/components/ui/button";

interface LoadingButtonProps extends ButtonProps {
  isLoading?: boolean;
  loadingText?: string;
}

export function LoadingButton({
  children,
  isLoading,
  loadingText,
  disabled,
  ...props
}: LoadingButtonProps) {
  return (
    <Button disabled={disabled || isLoading} {...props}>
      {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
      {isLoading && loadingText ? loadingText : children}
    </Button>
  );
}

// Usage:
<LoadingButton isLoading={isSaving} loadingText="Saving...">
  Save Changes
</LoadingButton>
```

### 3.6 AdminButton (Redesigned)

**Purpose**: Indicate admin-required actions without looking destructive

```tsx
// components/custom/admin-button.tsx
import { ShieldAlert } from "lucide-react";
import { Button, type ButtonProps } from "~/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "~/components/ui/tooltip";

interface AdminButtonProps extends ButtonProps {
  tooltip?: string;
}

export function AdminButton({
  children = "Admin Required",
  tooltip = "This action requires admin privileges",
  ...props
}: AdminButtonProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button variant="secondary" disabled {...props}>
          <ShieldAlert className="mr-2 h-4 w-4" />
          {children}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{tooltip}</TooltipContent>
    </Tooltip>
  );
}

// Usage:
<AdminButton tooltip="Only admins can add players" />
<AdminButton>Waiting for admin</AdminButton>
```

### 3.7 ConfirmButton (with AlertDialog)

**Purpose**: Actions that require confirmation

```tsx
// components/custom/confirm-button.tsx
import { Button, type ButtonProps } from "~/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "~/components/ui/alert-dialog";

interface ConfirmButtonProps extends ButtonProps {
  title: string;
  description: string;
  confirmText?: string;
  cancelText?: string;
  onConfirm: () => void;
  destructive?: boolean;
}

export function ConfirmButton({
  children,
  title,
  description,
  confirmText = "Confirm",
  cancelText = "Cancel",
  onConfirm,
  destructive = false,
  variant,
  ...props
}: ConfirmButtonProps) {
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button variant={variant ?? (destructive ? "destructive" : "default")} {...props}>
          {children}
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{cancelText}</AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            className={destructive ? "bg-destructive hover:bg-destructive/90" : undefined}
          >
            {confirmText}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

// Usage:
<ConfirmButton
  title="Delete Tournament?"
  description="This action cannot be undone."
  confirmText="Delete"
  onConfirm={handleDelete}
  destructive
>
  <Trash2 className="mr-2 h-4 w-4" />
  Delete
</ConfirmButton>
```

---

## 4. Component Directory Structure

```
frontend/app/components/
├── ui/                           # shadcn primitives (don't modify)
│   └── button.tsx               # Base Button component
├── custom/                       # Custom button wrappers
│   ├── submit-button.tsx        # Form submissions
│   ├── cancel-button.tsx        # Modal/form cancellation
│   ├── loading-button.tsx       # Generic with loading state
│   ├── destructive-button.tsx   # Delete/remove actions
│   ├── icon-button.tsx          # Icon-only with accessibility
│   ├── admin-button.tsx         # Admin-required indicator
│   └── confirm-button.tsx       # Actions with confirmation
└── reusable/                     # (deprecated - migrate to custom/)
    ├── adminButton.tsx          # -> custom/admin-button.tsx
    ├── deleteButton.tsx         # -> custom/destructive-button.tsx
    └── addButton.tsx            # -> custom/icon-button.tsx
```

---

## 5. Migration Priority

### High Priority (Immediate)
1. **SubmitButton**: Used in every form modal
2. **CancelButton**: Used in every form modal
3. **DestructiveButton**: Multiple inconsistent delete patterns

### Medium Priority
4. **IconButton**: Navigation and action icons
5. **LoadingButton**: Generic async actions
6. **ConfirmButton**: Delete confirmations

### Low Priority
7. **AdminButton**: Less common, existing pattern works

---

## 6. Base Button Component Issue

The current base Button component wraps everything in a `motion.div`:

```tsx
// Current button.tsx
function Button({ ... }) {
  return (
    <motion.div whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
      <Comp ... />
    </motion.div>
  );
}
```

**Issues**:
1. Extra wrapper div affects flex layouts
2. Cannot be used with `asChild` properly (Link components)
3. Double animation when AdminOnlyButton wraps with another motion.div
4. Scale animation may not be desired for all buttons

**Recommendation**: Remove motion wrapper from base Button, add animation to specific custom components that need it.

---

## 7. Files Requiring Updates

| Category | File Count | Example Files |
|----------|-----------|---------------|
| Form Modals | 8 | CreateOrganizationModal, CreateLeagueModal, TournamentEditForm |
| Delete Buttons | 5 | tournament/deleteButton, game/deleteButton, user/deleteButton |
| Draft Buttons | 6 | choosePlayerButtons, initDraftDialog, undoPickButton |
| Navigation | 4 | prevButton, nextButton, TournamentFilterBar |
| Toolbar Buttons | 2 | BracketToolbar, zoom-slider |

---

## Next Steps

1. Create `components/custom/` directory
2. Implement SubmitButton, CancelButton, DestructiveButton first
3. Create migration script to find/replace patterns
4. Update form modals to use new components
5. Deprecate old reusable components
6. Address base Button motion.div issue
