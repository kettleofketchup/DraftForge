# Button Grouping Report

This report categorizes all buttons in the DraftForge frontend for creating custom button components.

**Generated**: 2026-01-25
**Analyzed Directories**: `frontend/app/components/`, `frontend/app/pages/`, `frontend/app/features/`

---

## Current Button System

The codebase uses shadcn/ui Button component with the following variants defined in `components/ui/button.tsx`:

```typescript
variant: {
  default: 'bg-primary text-primary-foreground shadow-xs hover:bg-primary/90',
  destructive: 'bg-destructive text-white shadow-xs hover:bg-destructive/90',
  outline: 'border bg-background shadow-xs hover:bg-accent hover:text-accent-foreground',
  secondary: 'bg-secondary text-secondary-foreground shadow-xs hover:bg-secondary/80',
  ghost: 'hover:bg-accent hover:text-accent-foreground',
  link: 'text-primary underline-offset-4 hover:underline',
}
size: { default, sm, lg, icon }
```

---

## 1. Delete/Destructive Buttons

| File | Line | Text/Icon | Current Styling | Loading? | Disabled? |
|------|------|-----------|-----------------|----------|-----------|
| components/reusable/deleteButton.tsx | 47-56 | `<Trash2>` icon | `variant="outline" size="sm" className="bg-red-950 hover:bg-red-600 text-white"` | No | Yes |
| components/tournament/card/deleteButton.tsx | 71-79 | `<Trash2>` icon | `variant="outline" size="sm" className="bg-red-950 hover:bg-red-600 text-white"` | No | Yes |
| components/user/userCard/deleteButton.tsx | 81-90 | `<Trash2>` icon | `variant="default" size="icon" className="bg-red-950 hover:bg-red-600 text-white hover:shadow-sm hover:shadow-red-500/50"` | No | Yes |
| components/game/gameCard/deleteButton.tsx | 52-60 | `<Trash2>` icon | `variant="outline" size="sm" className="bg-red-950 hover:bg-red-600 text-white"` | No | Yes |
| pages/tournament/tabs/players/playerRemoveButton.tsx | 107-117 | `<Trash2>` icon | `variant="outline" size="sm" className="bg-red-950 hover:bg-red-600 text-white"` | No | Yes |
| components/bracket/controls/BracketToolbar.tsx | 107 | "Reset" | `variant="destructive"` | No | No |
| components/draft/buttons/initDraftDialog.tsx | 84-87 | "Restart Draft" | `variant="destructive" className="w-40 sm:w-20%"` | No | No |
| components/navbar/login.tsx | 142-145 | "Logout" | `variant="destructive"` | No | No |
| components/herodraft/HeroDraftModal.tsx | 508-517 | "Close" (X icon) | `variant="destructive" size="sm"` | No | No |
| components/tournament/captains/UpdateCaptainButton.tsx | 72 | "Remove Captain" | `variant="destructive"` (dynamic) | No | No |

### Inconsistencies Found
- Delete buttons use 3 different patterns:
  1. `variant="outline"` + custom red classes (most common)
  2. `variant="default"` + custom red classes
  3. `variant="destructive"` (native shadcn)
- Shadow effects inconsistently applied (`hover:shadow-sm hover:shadow-red-500/50` only on user delete)
- Size varies: `size="sm"`, `size="icon"`, or default

### Recommended Custom Component: `DestructiveButton`
- **Base**: `variant="destructive"` (use native shadcn destructive)
- **Required props**: `onClick`, `children`
- **Optional props**: `loading`, `disabled`, `icon`, `size`, `confirmDialog`
- **Minimum Tailwind**: Native `destructive` variant handles this:
  ```css
  bg-destructive text-white shadow-xs hover:bg-destructive/90
  ```
- **For icon-only delete**: Create `DeleteIconButton` with `size="icon"` and `<Trash2>` icon

---

## 2. Edit Buttons

| File | Line | Text/Icon | Current Styling | Loading? | Disabled? |
|------|------|-----------|-----------------|----------|-----------|
| components/tournament/card/TournamentCard.tsx | 253-260 | "Edit" + `<Edit>` icon | `className="w-20 ml-0 bg-purple-900 text-white"` | No | No |
| components/game/gameCard/gameCard.tsx | 158-165 | "Edit" + `<Edit>` icon | `className="w-20 ml-0 bg-purple-900 text-white"` | No | No |
| components/user/userCard/editModal.tsx | 116-123 | `<Edit2>` icon only | `size="icon" variant="default" className="bg-green-950 hover:bg-green-800 text-white hover:shadow-sm hover:shadow-green-500/50"` | No | No |
| components/organization/forms/EditOrganizationModal.tsx | 223-228 | "Save Changes" | `type="submit" disabled={isSubmitting}` | Yes ("Saving...") | Yes |

### Inconsistencies Found
- Edit toggle buttons use purple (`bg-purple-900`)
- Edit save buttons use green (`bg-green-950`) or default
- Icon-only edit uses green

### Recommended Custom Component: `EditButton`
- **Base**: Custom variant or className
- **Required props**: `onClick`
- **Optional props**: `editMode` (for toggle text), `icon`
- **Minimum Tailwind**:
  ```css
  bg-purple-900 hover:bg-purple-700 text-white
  ```

---

## 3. Confirm/Submit Buttons

| File | Line | Text/Icon | Current Styling | Loading? | Disabled? |
|------|------|-----------|-----------------|----------|-----------|
| components/organization/forms/CreateOrganizationModal.tsx | 150 | "Create" | `type="submit" disabled={isSubmitting}` | Yes ("Creating...") | Yes |
| components/organization/forms/EditOrganizationModal.tsx | 223-228 | "Save Changes" | `type="submit" disabled={isSubmitting}` | Yes ("Saving...") | Yes |
| components/league/forms/CreateLeagueModal.tsx | 159 | "Create" | `type="submit" disabled={isSubmitting}` | Yes ("Creating...") | Yes |
| components/league/EditLeagueModal.tsx | 189 | "Save Changes" | `disabled={isSubmitting}` | Yes ("Saving...") | Yes |
| components/tournament/card/TournamentCard.tsx | 193-202 | "Save Changes" / "Create Tournament" | `type="submit" className="btn btn-primary btn-sm mt-3" disabled={isSaving}` | Yes ("Saving...") | Yes |
| components/user/userCard/createModal.tsx | 145-170 | "Create User" / "Save Changes" | `className="bg-green-950 hover:bg-green-800 text-white hover:shadow-sm hover:shadow-green-500/50"` | Yes ("Saving...") | Yes |
| components/user/userCard/editModal.tsx | 75-99 | "Save Changes" / "Create User" | `className="bg-green-950 hover:bg-green-800 text-white hover:shadow-sm hover:shadow-green-500/50"` | Yes ("Saving...") | Yes |
| components/bracket/modals/AutoAssignModal.tsx | 227-240 | "Apply X Assignments" | `disabled={isApplying \|\| !result?.assignments.length}` | Yes ("Applying..." + Loader2) | Yes |
| pages/tournament/tabs/teams/createTeamsButton.tsx | 105-112 | "Submit this" | `className="btn btn-success bg-green-900 text-white"` | No | No |
| pages/tournament/tabs/teams/randomTeamsModal.tsx | 112-119 | "Regenerate Teams" | `className="btn btn-info"` | No | No |
| components/draft/buttons/draftStyleModal.tsx | 144-149 | "Apply X Draft" | `disabled={selectedStyle === draft.draft_style}` | No | Yes |
| components/draft/buttons/choosePlayerButtons.tsx | 108 | "Pick" | (default) | No | No |
| pages/profile/profile.tsx | 144 | "Submit" | `type="submit"` | No | No |

### Inconsistencies Found
- Mixed usage of DaisyUI classes (`btn btn-primary`, `btn btn-success`, `btn btn-info`) with shadcn
- Green submit buttons: `bg-green-950 hover:bg-green-800` or `bg-green-900`
- Loading states use text change ("Saving..." etc.) - no spinner icons except AutoAssignModal

### Recommended Custom Component: `SubmitButton`
- **Base**: `type="submit"` or `variant="default"`
- **Required props**: `onClick` or form context, `children`
- **Optional props**: `loading`, `disabled`, `loadingText`
- **Minimum Tailwind**:
  ```css
  bg-primary text-primary-foreground hover:bg-primary/90
  ```
  Or for green variant:
  ```css
  bg-green-700 hover:bg-green-600 text-white
  ```

---

## 4. Cancel Buttons

| File | Line | Text/Icon | Current Styling | Loading? | Disabled? |
|------|------|-----------|-----------------|----------|-----------|
| components/organization/forms/CreateOrganizationModal.tsx | 142-148 | "Cancel" | `type="button" variant="outline" disabled={isSubmitting}` | No | Yes |
| components/organization/forms/EditOrganizationModal.tsx | 215-221 | "Cancel" | `type="button" variant="outline" disabled={isSubmitting}` | No | Yes |
| components/league/forms/CreateLeagueModal.tsx | 151-157 | "Cancel" | `type="button" variant="outline" disabled={isSubmitting}` | No | Yes |
| components/league/EditLeagueModal.tsx | 181-187 | "Cancel" | `type="button" variant="outline"` | No | No |
| components/user/userCard/editModal.tsx | 102 | "Cancel" | `variant="outline"` | No | No |
| components/user/userCard/createModal.tsx | 173 | "Cancel" | `className="justify-right"` | No | No |
| components/draft/buttons/draftStyleModal.tsx | 319 | "Cancel" | `variant="outline"` | No | No |
| components/team/teamCard/createModal.tsx | 106 | "Cancel" | `variant="outline"` | No | No |
| components/team/teamCard/editModal.tsx | 82 | "Cancel" | `variant="outline"` | No | No |
| components/game/create/createGameModal.tsx | 70 | "Cancel" | `variant="outline"` | No | No |
| pages/tournament/tabs/players/addPlayerModal.tsx | 118 | "Cancel" | `variant="outline"` | No | No |
| pages/tournament/tabs/teams/randomTeamsModal.tsx | 133 | "Close" | `variant="outline"` | No | No |
| components/bracket/modals/AutoAssignModal.tsx | 224 | "Cancel" | `variant="outline"` | No | No |
| components/tournament/captains/captainSelectionModal.tsx | 71 | "Close" | `variant="outline"` | No | No |

### Consistency Status
- **Highly consistent**: Almost all use `variant="outline"`
- One outlier uses `className="justify-right"` without variant

### Recommended Custom Component: `CancelButton`
- **Base**: `variant="outline"`
- **Required props**: `onClick` or DialogClose wrapper
- **Optional props**: `disabled`
- **Minimum Tailwind**: Native `outline` variant:
  ```css
  border bg-background shadow-xs hover:bg-accent hover:text-accent-foreground
  ```

---

## 5. Primary CTA Buttons

| File | Line | Text/Icon | Current Styling | Loading? | Disabled? |
|------|------|-----------|-----------------|----------|-----------|
| pages/home/home.tsx | 170-175 | "Browse Tournaments" | `size="lg" className="!text-black" asChild` | No | No |
| pages/home/home.tsx | 273-275 | "Get Started" | `size="lg" className="!text-black" asChild` | No | No |
| components/draft/draftModal.tsx | 385-391 | "Live Draft" / "Start Draft" | `className="bg-green-800 hover:bg-green-600" / "bg-sky-800 hover:bg-sky-600"` | No | No |
| components/tournament/captains/captainSelectionModal.tsx | 36-41 | "Pick Captains" | `className="bg-yellow-400 hover:bg-yellow-200 text-black"` | No | No |
| pages/tournament/tabs/teams/randomTeamsModal.tsx | 82-89 | "Create Teams" | `className="btn btn-primary"` | No | No |
| pages/tournament/tabs/players/addPlayerModal.tsx | 73-84 | `<PlusCircle>` icon | `size="icon" variant="default" className="bg-green-950 hover:bg-green-800 text-white hover:shadow-sm hover:shadow-green-500/50"` | No | No |
| components/navbar/login.tsx | 134-137 | "Profile" | (default inside dropdown) | No | No |
| components/draft/buttons/draftStyleModal.tsx | 108-114 | "Draft Style" | `className="bg-blue-500 hover:bg-blue-600 text-white" variant="default"` | No | No |

### Inconsistencies Found
- Primary CTAs use many different colors: green, sky blue, yellow, blue, primary
- `!text-black` override needed for home page CTAs (indicates theme issue)

### Recommended Custom Component: `PrimaryButton`
- **Base**: `variant="default"` with optional color prop
- **Required props**: `children`
- **Optional props**: `size`, `asChild`, `color` (green/blue/yellow)
- **Minimum Tailwind**: Native `default` variant or themed:
  ```css
  bg-primary text-primary-foreground shadow-xs hover:bg-primary/90
  ```

---

## 6. Secondary Buttons

| File | Line | Text/Icon | Current Styling | Loading? | Disabled? |
|------|------|-----------|-----------------|----------|-----------|
| components/tournament/card/TournamentCard.tsx | 266-272 | "View" | `variant="secondary" className="w-20 outline-green-500"` | No | No |
| components/game/gameCard/gameCard.tsx | 173-181 | "Stats" | `variant="secondary" className="w-24 outline-green-500"` | No | No |
| components/bracket/modals/MatchStatsModal.tsx | 194-201 | "View Stats" | `variant="secondary" size="sm"` | No | No |
| pages/home/home.tsx | 176-180 | "Join Discord" | `size="lg" variant="outline" className="shadow-md border-2 border-emerald-500 text-emerald-400 hover:bg-emerald-500/20"` | No | No |
| pages/home/home.tsx | 276-278 | "Learn More" | `size="lg" variant="outline" className="shadow-md border-2 border-violet-500 text-violet-400 hover:bg-violet-500/20"` | No | No |
| components/herodraft/HeroDraftModal.tsx | 474-482 | `<Send>` icon | `variant="secondary" size="icon" disabled` | No | Yes |

### Inconsistencies Found
- Mix of `variant="secondary"` and `variant="outline"` with custom borders
- Home page uses colored outlines (emerald, violet)

### Recommended Custom Component: `SecondaryButton`
- **Base**: `variant="secondary"`
- **Required props**: `children`
- **Optional props**: `size`, `borderColor`
- **Minimum Tailwind**: Native `secondary` variant:
  ```css
  bg-secondary text-secondary-foreground shadow-xs hover:bg-secondary/80
  ```

---

## 7. Warning Buttons

| File | Line | Text/Icon | Current Styling | Loading? | Disabled? |
|------|------|-----------|-----------------|----------|-----------|
| components/draft/buttons/undoPickButton.tsx | 79-86 | "Undo" + `<Undo2>` icon | `variant="outline" className="bg-orange-900/50 border-orange-600 text-orange-400 hover:bg-orange-800/50" disabled={isLoading}` | Yes | Yes |
| components/reusable/adminButton.tsx | 31-34 | "Must be Admin" | `className="btn btn-danger bg-red-900 text-white"` | No | No |

### Inconsistencies Found
- Warning uses orange theme
- AdminOnlyButton uses red (overlaps with destructive)

### Recommended Custom Component: `WarningButton`
- **Base**: `variant="outline"` with orange theme
- **Required props**: `onClick`, `children`
- **Optional props**: `loading`, `disabled`, `icon`
- **Minimum Tailwind**:
  ```css
  bg-orange-900/50 border-orange-600 text-orange-400 hover:bg-orange-800/50
  ```

---

## 8. Icon-Only Buttons

| File | Line | Icon | Current Styling | Loading? | Disabled? |
|------|------|------|-----------------|----------|-----------|
| components/reusable/deleteButton.tsx | 47 | `<Trash2>` | `variant="outline" size="sm"` | No | Yes |
| components/user/userCard/deleteButton.tsx | 81 | `<Trash2>` | `variant="default" size="icon"` | No | Yes |
| components/user/userCard/editModal.tsx | 116 | `<Edit2>` | `size="icon" variant="default"` | No | No |
| pages/tournament/tabs/players/addPlayerModal.tsx | 73 | `<PlusCircle>` | `size="icon" variant="default"` | No | No |
| components/draft/buttons/prevButton.tsx | 19 | `<ChevronsLeft>` | `className="bg-sky-900" size="icon"` | No | No |
| components/draft/buttons/nextButton.tsx | 20 | `<ChevronsRight>` | `className="bg-sky-900" size="icon"` | No | No |
| components/ui/zoom-slider.tsx | 36, 51, 58, 65 | Zoom icons | `variant="ghost" size="icon"` | No | Yes |
| components/herodraft/HeroDraftModal.tsx | 474 | `<Send>` | `variant="secondary" size="icon"` | No | Yes |

### Inconsistencies Found
- Icon buttons use `size="icon"` or `size="sm"` inconsistently
- Colors vary widely

### Recommended Custom Component: `IconButton`
- **Base**: `size="icon"`
- **Required props**: `icon` (React node), `ariaLabel`
- **Optional props**: `variant`, `disabled`, `tooltip`
- **Minimum Tailwind**: Inherits from variant, plus:
  ```css
  size-9 (from size="icon")
  ```

---

## 9. Navigation Buttons

| File | Line | Text/Icon | Current Styling | Loading? | Disabled? |
|------|------|-----------|-----------------|----------|-----------|
| components/draft/buttons/prevButton.tsx | 19 | `<ChevronsLeft>` | `className="bg-sky-900" size="icon"` | No | No |
| components/draft/buttons/nextButton.tsx | 20 | `<ChevronsRight>` | `className="bg-sky-900" size="icon"` | No | No |
| components/draft/buttons/latestButton.tsx | 19 | "Latest" | `className="bg-sky-900 text-white"` | No | No |
| features/leaderboard/LeaderboardPage.tsx | 64-70 | "Previous" | `variant="outline" size="sm" disabled={!data.previous}` | No | Yes |
| features/leaderboard/LeaderboardPage.tsx | 72-78 | "Next" | `variant="outline" size="sm" disabled={!data.next}` | No | Yes |
| components/tournament/TournamentFilterBar.tsx | 77-84 | "Filter" | `variant="outline" size="sm"` | No | No |
| components/tournament/TournamentFilterBar.tsx | 86-89 | "Clear filters" | `variant="ghost" size="sm"` | No | No |

### Recommended Custom Component: `NavButton`
- **Base**: `variant="outline"` or custom navigation style
- **Required props**: `onClick`, `direction` (prev/next) or `children`
- **Optional props**: `disabled`, `size`
- **Minimum Tailwind**: For draft navigation:
  ```css
  bg-sky-900 text-white hover:bg-sky-800
  ```

---

## 10. Dialog/Modal Close Buttons

| File | Line | Text/Icon | Current Styling | Loading? | Disabled? |
|------|------|-----------|-----------------|----------|-----------|
| components/draft/draftModal.tsx | 448 | "Close" | (default) | No | No |
| components/draft/buttons/shareDraftButton.tsx | 42 | "Copy" | (default) | No | No |
| components/bracket/modals/MatchStatsModal.tsx | 169-170 | "View Draft" / "Start Draft" | `variant="outline" size="sm"` | Yes (Loader2) | Yes |
| components/bracket/modals/LinkSteamMatchModal.tsx | 204 | "Link" | (default) | No | No |
| components/league/LeagueMatchCard.tsx | 158-164 | "View Details" | `variant="outline" size="sm" disabled={!hasSteamLink}` | No | Yes |

### Recommended Custom Component: `DialogCloseButton`
- **Base**: Default variant wrapped in `DialogClose`
- **Required props**: `children` or default "Close"
- **Optional props**: `variant`
- **Minimum Tailwind**: Native default:
  ```css
  bg-primary text-primary-foreground shadow-xs hover:bg-primary/90
  ```

---

## 11. Other Buttons

| File | Line | Text/Icon | Current Styling | Loading? | Disabled? |
|------|------|-----------|-----------------|----------|-----------|
| components/navbar/login.tsx | 157-178 | Discord Login | Custom `<button>` with SVG | No | No |
| components/herodraft/HeroDraftModal.tsx | 308-392 | Draft choice buttons | (default) with various disabled states | Yes | Yes |
| components/bracket/modals/DotaMatchStatsModal.tsx | 71-90 | Toggle buttons | `variant="outline" size="sm"` dynamic | No | No |
| components/bracket/modals/SteamMatchCard.tsx | 157-166 | "Link This" / "Remove Link" | (default) / `variant="destructive"` | No | No |
| components/admin-team/AdminTeamSection.tsx | Various | Tab/section buttons | Native `<button>` elements | No | No |
| components/herodraft/HeroGrid.tsx | 109 | Hero selection | Native `<button>` | No | Yes |
| components/herodraft/DraftTopBar.tsx | 106 | Fullscreen toggle | Native `<button>` | No | No |
| pages/about/sections/MaintainerSection.tsx | 43 | Social link | (default) asChild | No | No |

### Notes
- Login button is completely custom (not using shadcn Button)
- HeroDraft choice buttons could use a `ChoiceButton` component
- Native `<button>` elements in admin sections should be migrated to shadcn Button

---

## Summary: Proposed Custom Components

| Component | Extends | Key Styling | Use Cases |
|-----------|---------|-------------|-----------|
| `DestructiveButton` | Button `variant="destructive"` | Native destructive | Delete, Remove, Reset actions |
| `DeleteIconButton` | Button `size="icon"` | `<Trash2>` + destructive | Icon-only delete buttons |
| `EditButton` | Button | `bg-purple-900 hover:bg-purple-700` | Edit toggle buttons |
| `SubmitButton` | Button `type="submit"` | Loading state support | Form submissions |
| `CancelButton` | Button `variant="outline"` | Native outline | Cancel/Close actions |
| `PrimaryButton` | Button `variant="default"` | Theme-aware | Main CTAs |
| `SecondaryButton` | Button `variant="secondary"` | Native secondary | Less prominent actions |
| `WarningButton` | Button `variant="outline"` | Orange theme | Caution actions |
| `IconButton` | Button `size="icon"` | Icon + tooltip | Icon-only buttons |
| `NavButton` | Button | `bg-sky-900` or outline | Prev/Next navigation |

---

## Priority Fixes

1. **Standardize Delete Buttons**: All delete buttons should use `variant="destructive"` instead of custom red classes with `variant="outline"`

2. **Loading State Pattern**: Implement consistent loading state:
   ```tsx
   {isLoading ? (
     <>
       <Loader2 className="h-4 w-4 mr-2 animate-spin" />
       Loading...
     </>
   ) : (
     children
   )}
   ```

3. **Remove DaisyUI Mixins**: Remove `btn btn-primary`, `btn btn-danger`, `btn btn-success`, `btn btn-info` classes - use shadcn variants only

4. **Migrate Native Buttons**: Convert native `<button>` elements to shadcn `<Button>` for consistency

5. **Color Consistency**:
   - Green actions: `bg-green-700 hover:bg-green-600`
   - Blue navigation: `bg-sky-900 hover:bg-sky-800`
   - Purple edit: `bg-purple-900 hover:bg-purple-700`
   - Orange warning: `bg-orange-900/50 border-orange-600`
