# Modal and Dialog Patterns Audit

**Date**: 2026-01-25
**Purpose**: Audit all modal/dialog patterns in the frontend for mobile responsiveness and consistency

## Executive Summary

The codebase has **35+ modal/dialog implementations** across different feature areas. While the base shadcn Dialog component has been updated with responsive defaults (`max-w-[calc(100%-2rem)]`), individual implementations show significant inconsistencies in:

1. **Size configurations** - ranging from full-screen to fixed widths
2. **Button placement** - inconsistent Cancel/Confirm ordering
3. **Mobile responsiveness** - many don't work well at 375px
4. **Form patterns** - mixed usage of react-hook-form vs manual state

---

## 1. Current Modal/Dialog Patterns Found

### 1.1 Confirmation Dialogs (AlertDialog)

Used for destructive or important actions requiring user confirmation.

| File | Purpose | Mobile Issues |
|------|---------|---------------|
| `components/tournament/card/deleteButton.tsx` | Delete tournament | Green background color, no responsive sizing |
| `components/game/gameCard/deleteButton.tsx` | Delete game | Green background, identical to above |
| `components/draft/buttons/undoPickButton.tsx` | Undo draft pick | Default sizing, works okay |
| `components/draft/buttons/initDraftDialog.tsx` | Restart draft | Red background, motion wrapper adds complexity |
| `components/herodraft/HeroDraftModal.tsx` | Confirm hero pick/ban | Nested inside fullscreen modal |

**Current Implementation Example** (deleteButton.tsx):
```tsx
<AlertDialog>
  <AlertDialogTrigger asChild>
    <Button variant="outline" size="sm" disabled={disabled} aria-label="Delete"
      className="bg-red-950 hover:bg-red-600 text-white">
      <Trash2 className="h-4 w-4" color="red" />
    </Button>
  </AlertDialogTrigger>
  <AlertDialogContent className={`bg-green-900`}>  {/* Inconsistent color */}
    <AlertDialogHeader>
      <AlertDialogTitle>Delete Tournament?</AlertDialogTitle>
      <AlertDialogDescription className="text-base-700">
        This removes tournament {tournament.pk}
      </AlertDialogDescription>
    </AlertDialogHeader>
    <AlertDialogFooter>
      <AlertDialogCancel>Cancel</AlertDialogCancel>
      <AlertDialogAction onClick={handleChange}>Confirm Delete</AlertDialogAction>
    </AlertDialogFooter>
  </AlertDialogContent>
</AlertDialog>
```

**Issues Identified**:
- Inconsistent background colors (green for delete, red for restart)
- No loading states on action buttons
- Button text varies ("Confirm Delete" vs "RestartDraft" vs "Undo Pick")

---

### 1.2 Form Dialogs (Dialog + Form)

Used for creating/editing entities with multiple form fields.

| File | Purpose | Sizing | Mobile Issues |
|------|---------|--------|---------------|
| `components/tournament/create/createModal.tsx` | Create tournament | `DIALOG_CSS` (full-screen) | Requires scroll |
| `components/league/forms/CreateLeagueModal.tsx` | Create league | Default | Works okay |
| `components/organization/forms/CreateOrganizationModal.tsx` | Create org | Default | Works okay |
| `components/league/EditLeagueModal.tsx` | Edit league | Default | Works okay |
| `components/user/userCard/editModal.tsx` | Edit user | `DIALOG_CSS_SMALL` | Custom sizing |

**Two Patterns Identified**:

**Pattern A: react-hook-form + Zod** (recommended):
```tsx
// CreateLeagueModal.tsx - Clean, validated
const form = useForm<CreateLeagueInput>({
  resolver: zodResolver(CreateLeagueSchema),
  defaultValues: { name: '', description: '' },
});

<Form {...form}>
  <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
    <FormField control={form.control} name="name" render={({ field }) => (
      <FormItem>
        <FormLabel>Name</FormLabel>
        <FormControl><Input {...field} /></FormControl>
        <FormMessage />
      </FormItem>
    )} />
    <DialogFooter>
      <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
      <Button type="submit" disabled={isSubmitting}>Create</Button>
    </DialogFooter>
  </form>
</Form>
```

**Pattern B: Manual state management** (legacy):
```tsx
// UserEditModal.tsx - More complex, less consistent
const [form, setForm] = useState<UserType>(initialValues);
const [errorMessage, setErrorMessage] = useState({});

<form onSubmit={onSubmit}>
  <UserEditForm user={user} form={form} setForm={setForm} />
</form>
<DialogFooter>
  <DialogClose asChild>
    <Button onClick={handleSave}>Save Changes</Button>
  </DialogClose>
  <DialogClose asChild>
    <Button variant="outline">Cancel</Button>
  </DialogClose>
</DialogFooter>
```

**Issues Identified**:
- Button order inconsistent (Cancel first vs Submit first)
- Some use `DialogClose` on submit button (closes before action completes)
- Loading state text varies ("Creating...", "Saving...", "Submitting...")

---

### 1.3 Display/Information Dialogs

Read-only modals showing details without form submission.

| File | Purpose | Sizing | Mobile Issues |
|------|---------|--------|---------------|
| `components/player/PlayerModal.tsx` | Player profile | `max-w-md` | Works well |
| `components/team/TeamModal.tsx` | Team details | `max-w-2xl` | Table may overflow |
| `components/draft/DraftEventModal.tsx` | Draft history | `max-w-md` | Works well |
| `components/herodraft/HeroDraftHistoryModal.tsx` | Hero draft history | `max-w-md` | Works well |
| `components/bracket/modals/MatchStatsModal.tsx` | Match details | `max-w-2xl` | Grid may overflow |

**Good Pattern Example** (DraftEventModal.tsx):
```tsx
<Dialog open={open} onOpenChange={onOpenChange}>
  <DialogContent className="max-w-md">
    <DialogHeader>
      <DialogTitle>Draft Event History</DialogTitle>
    </DialogHeader>
    <ScrollArea className="h-[400px] pr-4">
      {/* Content */}
    </ScrollArea>
  </DialogContent>
</Dialog>
```

---

### 1.4 Full-Screen/Complex Modals

Modals that take over the entire screen or have complex layouts.

| File | Purpose | Sizing | Mobile Issues |
|------|---------|--------|---------------|
| `components/draft/draftModal.tsx` | Main draft UI | `DIALOG_CSS` | Very complex, needs review |
| `components/draft/buttons/draftStyleModal.tsx` | Draft style config | `DIALOG_CSS max-w-2xl` | Mixed sizing |
| `components/herodraft/HeroDraftModal.tsx` | Hero draft | Full-screen custom | Shows "Under Construction" on mobile |
| `components/bracket/modals/AutoAssignModal.tsx` | Auto-assign matches | `max-w-2xl max-h-[80vh]` | Good pattern |
| `components/bracket/modals/LinkSteamMatchModal.tsx` | Link Steam match | `max-w-2xl max-h-[80vh]` | Good pattern |

**HeroDraftModal Full-Screen Pattern**:
```tsx
<DialogContent
  className="!fixed !inset-0 !translate-x-0 !translate-y-0 !top-0 !left-0 !max-w-none !w-full !h-full !p-0 !gap-0 !rounded-none !border-0 bg-gray-900 overflow-hidden"
  showCloseButton={false}
  onInteractOutside={(e) => e.preventDefault()}
  onEscapeKeyDown={(e) => e.preventDefault()}
>
```

**Issues Identified**:
- `DIALOG_CSS` from modal.tsx is overly aggressive: `min-w-full xl:min-w-[98%] sm:h-[95vh] sm:max-h-[95vh]`
- Inconsistent use of ScrollArea vs overflow-auto
- Some modals prevent closing (hero draft), which may frustrate users

---

### 1.5 Share/Action Dialogs

Simple dialogs with a single action.

| File | Purpose | Mobile Issues |
|------|---------|---------------|
| `components/draft/buttons/shareDraftButton.tsx` | Share draft URL | Works well, simple |

**Good Simple Pattern**:
```tsx
<Dialog>
  <DialogTrigger asChild>
    <Button variant="outline"><Share2 className="mr-2 h-4 w-4" /> Share</Button>
  </DialogTrigger>
  <DialogContent>
    <DialogHeader>
      <DialogTitle>Share Draft</DialogTitle>
      <DialogDescription>Share this URL with others...</DialogDescription>
    </DialogHeader>
    <div className="flex items-center space-x-2">
      <Input value={shareUrl} readOnly />
      <Button onClick={copyToClipboard}>Copy</Button>
    </div>
  </DialogContent>
</Dialog>
```

---

## 2. Mobile Responsiveness Analysis (375px)

### Current Base Dialog Styling

The `dialog.tsx` component has good responsive defaults:
```tsx
className={cn(
  "bg-background data-[state=open]:animate-in ... fixed top-[50%] left-[50%] z-50 grid w-full max-w-[calc(100%-2rem)] translate-x-[-50%] translate-y-[-50%] gap-4 rounded-lg border p-6 shadow-lg duration-200 sm:max-w-lg",
  className
)}
```

**What works**:
- `max-w-[calc(100%-2rem)]` ensures 1rem margin on mobile
- `sm:max-w-lg` limits width on desktop

**What doesn't work**:
- Custom `DIALOG_CSS` overrides these good defaults
- `max-w-2xl` class exceeds mobile screen width
- Fixed heights like `h-[80vh]` can be too tall on landscape mobile

### Issues at 375px Width

1. **Tournament Create Modal**: Uses `DIALOG_CSS` which sets `min-w-full xl:min-w-[98%]` - takes entire screen, no visual modal feel
2. **Team Modal**: `max-w-2xl` = 672px, exceeds 375px, horizontal scroll may occur
3. **Match Stats Modal**: Grid layout (`grid-cols-3`) doesn't stack on mobile
4. **Draft Modal**: Extremely complex, footer buttons don't fit
5. **Hero Draft Modal**: Explicitly shows "Mobile View Under Construction"

---

## 3. Inconsistencies Identified

### 3.1 Button Placement Inconsistencies

| Pattern | Files Using |
|---------|-------------|
| `<Cancel> <Submit>` (correct) | CreateLeagueModal, CreateOrganizationModal, UndoPickButton |
| `<Submit> <Cancel>` (reversed) | UserEditModal |
| `<Cancel>` on left, `<Submit>` on right with gap | AutoAssignModal |

### 3.2 Background Color Inconsistencies

| Color | Usage |
|-------|-------|
| `bg-green-900` | Delete tournament, Delete game (should be red/destructive) |
| `bg-red-900` | Init draft restart |
| Default (dark) | Most others |
| `bg-orange-600` | Undo pick action button |

### 3.3 Loading State Text

| Text | Files |
|------|-------|
| `"Creating..."` | CreateLeagueModal, CreateOrganizationModal |
| `"Saving..."` | UserEditModal |
| `"Submitting..."` | HeroDraftModal |
| `"Applying..."` | AutoAssignModal |
| `"Loading..."` | Various |
| `"..."` | HeroDraftModal choice buttons (too short) |

### 3.4 Size Constants in modal.tsx

```tsx
export const DIALOG_CSS = 'min-w-full xl:min-w-[98%] sm:h-[95vh] sm:max-h-[95vh]';
export const SCROLLAREA_CSS = 'overflow-y-auto overflow-x-auto h-screen max-h-[75vh] py-5em pr-2';
export const DIALOG_CSS_SMALL = 'min-w-[98vw] h-[100vh] max-h-[98vh] sm:min-w-[26.563em] sm:h-[85vh]';
export const SCROLLAREA_CSS_SMALL = 'overflow-y-auto overflow-x-auto max-h-[65vh] py-5em pr-2';
```

**Issues**:
- `py-5em` is invalid CSS (should be `py-5` or `py-20`)
- `min-w-full` forces full width on all screens
- Constants are too prescriptive, don't allow for modal content needs

---

## 4. Recommendations for Standardized Components

### 4.1 ConfirmDialog Component

For confirmation actions (delete, undo, destructive actions).

```tsx
// components/custom/ConfirmDialog.tsx
interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'default' | 'destructive' | 'warning';
  isLoading?: boolean;
  onConfirm: () => void | Promise<void>;
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'default',
  isLoading = false,
  onConfirm,
}: ConfirmDialogProps) {
  const variantStyles = {
    default: '',
    destructive: 'bg-destructive hover:bg-destructive/90',
    warning: 'bg-orange-600 hover:bg-orange-700',
  };

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent className="max-w-[calc(100%-2rem)] sm:max-w-md">
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter className="flex-col-reverse sm:flex-row gap-2">
          <AlertDialogCancel disabled={isLoading}>{cancelLabel}</AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            disabled={isLoading}
            className={variantStyles[variant]}
          >
            {isLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            {confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
```

**Usage**:
```tsx
<ConfirmDialog
  open={showDeleteConfirm}
  onOpenChange={setShowDeleteConfirm}
  title="Delete Tournament?"
  description="This action cannot be undone."
  confirmLabel="Delete"
  variant="destructive"
  isLoading={isDeleting}
  onConfirm={handleDelete}
/>
```

---

### 4.2 FormDialog Component

For create/edit forms with consistent layout.

```tsx
// components/custom/FormDialog.tsx
interface FormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: React.ReactNode;
  submitLabel?: string;
  cancelLabel?: string;
  isSubmitting?: boolean;
  onSubmit: () => void | Promise<void>;
  size?: 'sm' | 'md' | 'lg' | 'xl' | 'full';
}

const sizeClasses = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
  xl: 'max-w-2xl',
  full: 'max-w-[calc(100%-2rem)] sm:max-w-4xl',
};

export function FormDialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  submitLabel = 'Save',
  cancelLabel = 'Cancel',
  isSubmitting = false,
  onSubmit,
  size = 'md',
}: FormDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={cn('max-w-[calc(100%-2rem)]', sizeClasses[size])}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>

        <div className="max-h-[60vh] overflow-y-auto py-4">
          {children}
        </div>

        <DialogFooter className="flex-col-reverse sm:flex-row gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isSubmitting}
          >
            {cancelLabel}
          </Button>
          <Button onClick={onSubmit} disabled={isSubmitting}>
            {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {submitLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

---

### 4.3 InfoDialog Component

For displaying read-only information.

```tsx
// components/custom/InfoDialog.tsx
interface InfoDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  children: React.ReactNode;
  size?: 'sm' | 'md' | 'lg';
  showClose?: boolean;
}

export function InfoDialog({
  open,
  onOpenChange,
  title,
  children,
  size = 'md',
  showClose = true,
}: InfoDialogProps) {
  const sizeClasses = {
    sm: 'max-w-sm',
    md: 'max-w-md',
    lg: 'max-w-2xl',
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={cn('max-w-[calc(100%-2rem)]', sizeClasses[size])}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <ScrollArea className="max-h-[60vh]">
          {children}
        </ScrollArea>
        {showClose && (
          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Close
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
}
```

---

### 4.4 MobileSheet Component

For mobile-friendly bottom sheets (alternative to dialogs on small screens).

```tsx
// components/custom/ResponsiveDialog.tsx
import { useMediaQuery } from '@uidotdev/usehooks';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import {
  Drawer,
  DrawerContent,
  DrawerHeader,
  DrawerTitle,
} from '~/components/ui/drawer';

interface ResponsiveDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  children: React.ReactNode;
}

export function ResponsiveDialog({
  open,
  onOpenChange,
  title,
  children,
}: ResponsiveDialogProps) {
  const isDesktop = useMediaQuery('(min-width: 640px)');

  if (isDesktop) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
          </DialogHeader>
          {children}
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent className="max-h-[85vh]">
        <DrawerHeader>
          <DrawerTitle>{title}</DrawerTitle>
        </DrawerHeader>
        <div className="px-4 pb-4 overflow-y-auto">
          {children}
        </div>
      </DrawerContent>
    </Drawer>
  );
}
```

**Note**: Requires adding shadcn Drawer component: `npx shadcn@latest add drawer`

---

## 5. Migration Priority

### High Priority (User-facing, broken on mobile)

1. **Delete confirmation dialogs** - Fix green background, standardize to ConfirmDialog
2. **Tournament create modal** - Remove `DIALOG_CSS`, use FormDialog
3. **Draft modal footer** - Buttons overflow on mobile

### Medium Priority (Inconsistent but functional)

4. **Form dialogs** - Standardize button order to Cancel/Submit
5. **User edit modal** - Migrate to react-hook-form pattern
6. **Loading state text** - Standardize to "Saving..." for forms, "Processing..." for actions

### Low Priority (Minor improvements)

7. **Info dialogs** - Already work well, wrap in InfoDialog for consistency
8. **Share dialog** - Simple, works well

---

## 6. Files to Modify

| File | Change |
|------|--------|
| `components/reusable/modal.tsx` | **DELETE** - Replace with custom components |
| `components/tournament/card/deleteButton.tsx` | Use ConfirmDialog, fix colors |
| `components/game/gameCard/deleteButton.tsx` | Use ConfirmDialog, fix colors |
| `components/draft/buttons/undoPickButton.tsx` | Use ConfirmDialog with warning variant |
| `components/draft/buttons/initDraftDialog.tsx` | Use ConfirmDialog with destructive variant |
| `components/tournament/create/createModal.tsx` | Use FormDialog, remove DIALOG_CSS |
| `components/user/userCard/editModal.tsx` | Migrate to react-hook-form, use FormDialog |
| `components/draft/draftModal.tsx` | Mobile-specific redesign needed |

---

## 7. Testing Checklist

For each modal after migration:

- [ ] Opens correctly on desktop (1024px+)
- [ ] Opens correctly on tablet (768px)
- [ ] Opens correctly on mobile (375px)
- [ ] Content doesn't overflow horizontally
- [ ] Buttons are tappable (min 44px touch target)
- [ ] Can be dismissed (X button, backdrop click, Escape)
- [ ] Loading states show correctly
- [ ] Form validation works
- [ ] Accessibility: focus trap, aria labels
