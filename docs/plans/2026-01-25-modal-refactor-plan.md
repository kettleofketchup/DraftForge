# Modal Refactor Plan

**Date**: 2026-01-25
**Based on**: [Modal and Dialog Patterns Audit](./2026-01-25-responsiveness-modals-audit.md)

## Overview

Map all existing modal implementations to new standardized reusable modal components. This plan consolidates 35+ modal/dialog implementations into 4 reusable components with consistent styling, responsive behavior, and accessibility patterns.

## New Reusable Components to Create

### 1. ConfirmDialog

**Location**: `frontend/app/components/ui/dialogs/ConfirmDialog.tsx`

**Purpose**: Confirmation actions (delete, undo, destructive)

**Props**:
| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `open` | `boolean` | required | Controls dialog visibility |
| `onOpenChange` | `(open: boolean) => void` | required | Callback when open state changes |
| `title` | `string` | required | Dialog title |
| `description` | `string` | required | Description of the action |
| `confirmLabel` | `string` | `"Confirm"` | Text for confirm button |
| `cancelLabel` | `string` | `"Cancel"` | Text for cancel button |
| `variant` | `"default" \| "destructive" \| "warning"` | `"default"` | Visual style variant |
| `isLoading` | `boolean` | `false` | Shows loading spinner on confirm |
| `onConfirm` | `() => void \| Promise<void>` | required | Callback when confirmed |

**Variant Styles**:
- `default`: Standard confirm button styling
- `destructive`: Red background for delete/remove actions
- `warning`: Orange background for undo/revert actions

---

### 2. FormDialog

**Location**: `frontend/app/components/ui/dialogs/FormDialog.tsx`

**Purpose**: Create/edit forms with consistent layout

**Props**:
| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `open` | `boolean` | required | Controls dialog visibility |
| `onOpenChange` | `(open: boolean) => void` | required | Callback when open state changes |
| `title` | `string` | required | Dialog title |
| `description` | `string \| undefined` | `undefined` | Optional description text |
| `children` | `React.ReactNode` | required | Form content |
| `submitLabel` | `string` | `"Save"` | Text for submit button |
| `cancelLabel` | `string` | `"Cancel"` | Text for cancel button |
| `isSubmitting` | `boolean` | `false` | Shows loading state |
| `onSubmit` | `() => void \| Promise<void>` | required | Form submit callback |
| `size` | `"sm" \| "md" \| "lg" \| "xl" \| "full"` | `"md"` | Dialog width |

**Size Classes**:
- `sm`: `max-w-sm` (384px)
- `md`: `max-w-md` (448px)
- `lg`: `max-w-lg` (512px)
- `xl`: `max-w-2xl` (672px)
- `full`: `max-w-4xl` (896px)

---

### 3. InfoDialog

**Location**: `frontend/app/components/ui/dialogs/InfoDialog.tsx`

**Purpose**: Read-only information display

**Props**:
| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `open` | `boolean` | required | Controls dialog visibility |
| `onOpenChange` | `(open: boolean) => void` | required | Callback when open state changes |
| `title` | `string` | required | Dialog title |
| `children` | `React.ReactNode` | required | Content to display |
| `size` | `"sm" \| "md" \| "lg"` | `"md"` | Dialog width |
| `showClose` | `boolean` | `true` | Shows close button in footer |

---

### 4. ResponsiveDialog

**Location**: `frontend/app/components/ui/dialogs/ResponsiveDialog.tsx`

**Purpose**: Dialog on desktop, Drawer on mobile (requires shadcn Drawer)

**Props**:
| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `open` | `boolean` | required | Controls dialog visibility |
| `onOpenChange` | `(open: boolean) => void` | required | Callback when open state changes |
| `title` | `string` | required | Dialog title |
| `children` | `React.ReactNode` | required | Dialog content |

**Note**: Uses `useMediaQuery('(min-width: 640px)')` to detect desktop/mobile.

---

## Migration Mapping

### ConfirmDialog Migrations

| Current File | Current Implementation | New Usage | Variant |
|--------------|----------------------|-----------|---------|
| `components/tournament/card/deleteButton.tsx` | AlertDialog with green bg | ConfirmDialog | destructive |
| `components/game/gameCard/deleteButton.tsx` | AlertDialog with green bg | ConfirmDialog | destructive |
| `components/reusable/deleteButton.tsx` | AlertDialog | ConfirmDialog | destructive |
| `components/user/userCard/deleteButton.tsx` | AlertDialog | ConfirmDialog | destructive |
| `pages/tournament/tabs/players/playerRemoveButton.tsx` | AlertDialog | ConfirmDialog | destructive |
| `components/draft/buttons/undoPickButton.tsx` | AlertDialog with orange | ConfirmDialog | warning |
| `components/draft/buttons/initDraftDialog.tsx` | AlertDialog with red | ConfirmDialog | destructive |

**Total**: 7 files

---

### FormDialog Migrations

| Current File | Current Implementation | New Usage | Size |
|--------------|----------------------|-----------|------|
| `components/organization/forms/CreateOrganizationModal.tsx` | Dialog + Form | FormDialog | md |
| `components/organization/forms/EditOrganizationModal.tsx` | Dialog + Form | FormDialog | md |
| `components/league/forms/CreateLeagueModal.tsx` | Dialog + Form | FormDialog | md |
| `components/league/EditLeagueModal.tsx` | Dialog + Form | FormDialog | md |
| `components/user/userCard/createModal.tsx` | Dialog + manual state | FormDialog | md |
| `components/user/userCard/editModal.tsx` | Dialog + manual state | FormDialog | md |
| `components/team/teamCard/createModal.tsx` | Dialog + Form | FormDialog | md |
| `components/team/teamCard/editModal.tsx` | Dialog + Form | FormDialog | md |
| `components/game/create/createGameModal.tsx` | Dialog + Form | FormDialog | lg |
| `pages/tournament/tabs/players/addPlayerModal.tsx` | Dialog + Form | FormDialog | md |
| `pages/tournament/tabs/teams/randomTeamsModal.tsx` | Dialog | FormDialog | md |
| `components/tournament/captains/captainSelectionModal.tsx` | Dialog | FormDialog | lg |

**Total**: 12 files

---

### InfoDialog Migrations

| Current File | Current Implementation | New Usage | Size |
|--------------|----------------------|-----------|------|
| `components/player/PlayerModal.tsx` | Dialog with ScrollArea | InfoDialog | md |
| `components/team/TeamModal.tsx` | Dialog | InfoDialog | lg |
| `components/draft/DraftEventModal.tsx` | Dialog with ScrollArea | InfoDialog | md |
| `components/herodraft/HeroDraftHistoryModal.tsx` | Dialog with ScrollArea | InfoDialog | md |
| `components/bracket/modals/MatchStatsModal.tsx` | Dialog | InfoDialog | lg |
| `components/draft/buttons/shareDraftButton.tsx` | Dialog simple | InfoDialog | sm |

**Total**: 6 files

---

### Complex/Custom Modals (No direct migration)

| Current File | Reason |
|--------------|--------|
| `components/draft/draftModal.tsx` | Too complex, needs custom implementation |
| `components/herodraft/HeroDraftModal.tsx` | Full-screen custom, mobile under construction |
| `components/draft/buttons/draftStyleModal.tsx` | Complex form with multiple sections |
| `components/bracket/modals/AutoAssignModal.tsx` | Custom preview + apply workflow |
| `components/bracket/modals/LinkSteamMatchModal.tsx` | Custom search + link workflow |
| `components/tournament/create/createModal.tsx` | Multi-step wizard, needs custom handling |

**Total**: 6 files (require individual review)

---

## Files to Delete After Migration

| File | Reason |
|------|--------|
| `components/reusable/modal.tsx` | `DIALOG_CSS` and `DIALOG_CSS_SMALL` constants no longer needed |

---

## Implementation Order

### Phase 1: Create Components

1. **Create ConfirmDialog component**
   - Location: `frontend/app/components/ui/dialogs/ConfirmDialog.tsx`
   - Based on AlertDialog with variant support
   - Standardized button order (Cancel, Confirm)
   - Loading state with spinner

2. **Create FormDialog component**
   - Location: `frontend/app/components/ui/dialogs/FormDialog.tsx`
   - Consistent size classes
   - Scrollable content area with `max-h-[60vh]`
   - Standardized footer layout

3. **Create InfoDialog component**
   - Location: `frontend/app/components/ui/dialogs/InfoDialog.tsx`
   - Read-only display with optional close button
   - ScrollArea integration

4. **Add shadcn Drawer component**
   - Run: `npx shadcn@latest add drawer`
   - Required for ResponsiveDialog

5. **Create ResponsiveDialog component**
   - Location: `frontend/app/components/ui/dialogs/ResponsiveDialog.tsx`
   - Dialog on desktop (640px+)
   - Drawer on mobile

6. **Create index.ts exports**
   - Location: `frontend/app/components/ui/dialogs/index.ts`
   - Export all dialog components

### Phase 2: Migrate ConfirmDialog Usages (7 files)

7. Migrate `components/tournament/card/deleteButton.tsx`
8. Migrate `components/game/gameCard/deleteButton.tsx`
9. Migrate `components/reusable/deleteButton.tsx`
10. Migrate `components/user/userCard/deleteButton.tsx`
11. Migrate `pages/tournament/tabs/players/playerRemoveButton.tsx`
12. Migrate `components/draft/buttons/undoPickButton.tsx`
13. Migrate `components/draft/buttons/initDraftDialog.tsx`

### Phase 3: Migrate FormDialog Usages (12 files)

14. Migrate `components/organization/forms/CreateOrganizationModal.tsx`
15. Migrate `components/organization/forms/EditOrganizationModal.tsx`
16. Migrate `components/league/forms/CreateLeagueModal.tsx`
17. Migrate `components/league/EditLeagueModal.tsx`
18. Migrate `components/user/userCard/createModal.tsx`
19. Migrate `components/user/userCard/editModal.tsx`
20. Migrate `components/team/teamCard/createModal.tsx`
21. Migrate `components/team/teamCard/editModal.tsx`
22. Migrate `components/game/create/createGameModal.tsx`
23. Migrate `pages/tournament/tabs/players/addPlayerModal.tsx`
24. Migrate `pages/tournament/tabs/teams/randomTeamsModal.tsx`
25. Migrate `components/tournament/captains/captainSelectionModal.tsx`

### Phase 4: Migrate InfoDialog Usages (6 files)

26. Migrate `components/player/PlayerModal.tsx`
27. Migrate `components/team/TeamModal.tsx`
28. Migrate `components/draft/DraftEventModal.tsx`
29. Migrate `components/herodraft/HeroDraftHistoryModal.tsx`
30. Migrate `components/bracket/modals/MatchStatsModal.tsx`
31. Migrate `components/draft/buttons/shareDraftButton.tsx`

### Phase 5: Cleanup

32. Delete `components/reusable/modal.tsx` constants file
33. Verify no remaining imports of `DIALOG_CSS` or `DIALOG_CSS_SMALL`

### Phase 6: Testing

34. Test all modals at 375px width
35. Test all modals at 768px width
36. Test all modals at 1024px+ width
37. Verify keyboard navigation (Tab, Escape)
38. Verify screen reader accessibility

---

## Testing Checklist

For each migrated modal:

- [ ] Opens correctly on desktop (1024px+)
- [ ] Opens correctly on tablet (768px)
- [ ] Opens correctly on mobile (375px)
- [ ] Content doesn't overflow horizontally
- [ ] Buttons are tappable (min 44px touch target)
- [ ] Can be dismissed (X button, backdrop click, Escape)
- [ ] Loading states show correctly
- [ ] Form validation works (if applicable)
- [ ] Accessibility: focus trap, aria labels

---

## Standardization Guidelines

### Button Order

Always use `Cancel` then `Submit`:
```tsx
<DialogFooter className="flex-col-reverse sm:flex-row gap-2">
  <Button variant="outline" onClick={handleCancel}>Cancel</Button>
  <Button onClick={handleSubmit}>Submit</Button>
</DialogFooter>
```

### Loading State Text

| Action Type | Loading Text |
|-------------|--------------|
| Create forms | "Creating..." |
| Edit forms | "Saving..." |
| Delete actions | "Deleting..." |
| Generic actions | "Processing..." |

### Mobile Responsive Footer

Use `flex-col-reverse sm:flex-row` to stack buttons vertically on mobile with Submit on top:
```tsx
<DialogFooter className="flex-col-reverse sm:flex-row gap-2">
```

### Size Breakpoints

All dialog components should use:
- `max-w-[calc(100%-2rem)]` for mobile (1rem margin each side)
- `sm:max-w-{size}` for desktop constraint
