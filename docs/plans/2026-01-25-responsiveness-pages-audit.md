# Mobile-First Design Compliance Audit

**Date**: 2026-01-25
**Target Breakpoint**: 375px (Phone Portrait)
**Auditor**: Claude (Automated Audit)

## Summary

| Category | Count |
|----------|-------|
| Pages Audited | 17 routes + 2 feature pages |
| Mobile-Ready (Green) | 5 |
| Needs Responsive Fixes (Yellow) | 9 |
| Needs Custom Mobile View (Red) | 5 |

---

## Audit Methodology

Each page was analyzed for:
1. **Responsive Tailwind classes** - Use of `sm:`, `md:`, `lg:`, `xl:`, `2xl:` breakpoints
2. **Fixed widths** - Hard-coded pixel/rem widths that break on mobile
3. **Horizontal scrolling risks** - `flex-row` without `flex-wrap`, wide grids
4. **Oversized fonts/padding** - Typography and spacing too large for mobile
5. **Mobile-first approach** - Base styles targeting mobile, then scaling up

---

## Mobile-Ready Pages (Green)

These pages follow mobile-first principles and should render well at 375px.

### 1. Home Page (`/home`)
**File**: `/frontend/app/pages/home/home.tsx`

**Strengths**:
- Mobile-first responsive typography: `text-5xl md:text-7xl`
- Responsive button layout: `flex-col sm:flex-row`
- Responsive grid: `grid-cols-2 md:grid-cols-4`
- Fluid padding: `py-20 px-4`
- Uses `max-w-6xl mx-auto` for content containment

**Status**: Ready for mobile

---

### 2. About Page (`/about`)
**File**: `/frontend/app/pages/about/about.tsx`

**Strengths**:
- Mobile-first hero typography: `text-5xl md:text-6xl`
- Container with responsive padding: `container mx-auto px-6`
- Features grid: `grid-cols-1 md:grid-cols-2`
- Technology grid: `grid-cols-2 md:grid-cols-4`

**Status**: Ready for mobile

---

### 3. Profile Page (`/profile`)
**File**: `/frontend/app/pages/profile/profile.tsx`

**Strengths**:
- Mobile-first container: `container px-1 sm:mx-auto sm:p-4`
- Responsive layout: `flex-col sm:flex-row`
- Good form layout patterns

**Status**: Ready for mobile

---

### 4. User Detail Page (`/user/:pk`)
**File**: `/frontend/app/pages/user/user.tsx`

**Strengths**:
- Simple container layout: `container mx-auto p-4`
- Single card view scales well
- No complex grid layouts

**Status**: Ready for mobile

---

### 5. Blog Page (`/blog`)
**File**: `/frontend/app/pages/blog/blog.tsx`

**Strengths**:
- Simple centered layout with Placeholder component

**Note**: This is a placeholder page

**Status**: Ready for mobile (placeholder)

---

## Pages Needing Responsive Fixes (Yellow)

These pages have some responsive patterns but have specific issues that need addressing.

### 1. Tournaments Page (`/tournaments`)
**File**: `/frontend/app/pages/tournaments/tournaments.tsx`

**Issues**:
- Grid jumps from 1 to 2 columns: `grid-cols-1 md:grid-cols-2 lg:grid-cols-2`
- No `sm:` breakpoint for gradual scaling
- Card skeleton has `max-w-sm` which may not fill width on mobile

**Recommendations**:
```tsx
// Current
grid-cols-1 md:grid-cols-2 lg:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4

// Suggested - add sm breakpoint
grid-cols-1 sm:grid-cols-2 lg:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4
```

**Priority**: Medium

---

### 2. Tournament Detail Page (`/tournament/:pk`)
**File**: `/frontend/app/pages/tournament/TournamentDetailPage.tsx`

**Issues**:
- Title uses `flex-row` without `flex-wrap` - may overflow on mobile
- `ml-4` on date creates fixed gap that may squeeze on mobile
- `text-3xl` title may be too large for 375px

**Recommendations**:
```tsx
// Current
<div className="flex flex-row items-center mb-2">

// Suggested
<div className="flex flex-col sm:flex-row items-start sm:items-center gap-2 mb-2">

// Title sizing
className="text-2xl sm:text-3xl font-bold mb-4"
```

**Priority**: High

---

### 3. TournamentTabs Component
**File**: `/frontend/app/pages/tournament/tabs/TournamentTabs.tsx`

**Issues**:
- Tab triggers without explicit mobile sizing
- Complex gap classes: `sm:-p1 sm:gap-2` (typo: `-p1` should be `-p-1`)
- `TabsTrigger className="w-full"` may cause overflow with 3 tabs

**Recommendations**:
- Consider scrollable tabs on mobile
- Use smaller text on mobile: `text-sm sm:text-base`

**Priority**: High

---

### 4. Leagues Page (`/leagues`)
**File**: `/frontend/app/routes/leagues.tsx`

**Issues**:
- Filter dropdown has fixed width: `w-64` (256px) - may not fit on mobile
- Grid uses `md:` as first breakpoint without `sm:`
- Header `flex items-center justify-between` may wrap awkwardly

**Recommendations**:
```tsx
// Current filter
<div className="w-64">

// Suggested
<div className="w-full sm:w-64">

// Header
className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-6"
```

**Priority**: Medium

---

### 5. League Detail Page (`/leagues/:leagueId`)
**File**: `/frontend/app/routes/league.tsx`

**Issues**:
- Header uses `flex items-start justify-between` - button may overflow
- `text-3xl` title without mobile sizing
- Badge group may overflow on mobile

**Recommendations**:
```tsx
// Title
<h1 className="text-2xl sm:text-3xl font-bold">

// Header layout
<div className="flex flex-col sm:flex-row items-start sm:justify-between gap-4">
```

**Priority**: Medium

---

### 6. Organizations Page (`/organizations`)
**File**: `/frontend/app/routes/organizations.tsx`

**Issues**:
- Same grid pattern as Leagues: `md:grid-cols-2` without `sm:`
- Header layout may wrap awkwardly on mobile

**Recommendations**:
- Same fixes as Leagues page

**Priority**: Medium

---

### 7. Organization Detail Page (`/organization/:id`)
**File**: `/frontend/app/routes/organization.tsx`

**Issues**:
- Logo section `w-32 h-32` is fixed - good size but layout needs work
- `flex-col md:flex-row` is correct but spacing may need adjustment
- `text-3xl` title without mobile sizing

**Recommendations**:
```tsx
// Good pattern already in use:
<div className="flex flex-col md:flex-row gap-6">

// Title needs mobile size
<h1 className="text-2xl sm:text-3xl font-bold">
```

**Priority**: Low

---

### 8. Users Page (`/users`)
**File**: `/frontend/app/pages/users/users.tsx`

**Issues**:
- Search header uses `grid-cols-4` - may be too rigid for mobile
- Grid gap classes vary: `gap-2 md:gap-4 lg:gap-6` - good
- Skeleton card has responsive classes but actual cards may not

**Recommendations**:
```tsx
// Current header grid
grid-cols-4

// Suggested - responsive header
<div className="flex flex-col sm:flex-row gap-4 items-stretch sm:items-center w-full">
```

**Priority**: Medium

---

### 9. Leaderboard Page (`/leaderboard`)
**File**: `/frontend/app/features/leaderboard/LeaderboardPage.tsx`

**Issues**:
- Table-based layout will overflow on 375px
- Pagination controls `flex items-center justify-between` may stack poorly
- `text-3xl` title without mobile sizing

**Recommendations**:
- Add horizontal scroll wrapper for table
- Consider card-based mobile view (see Red section for details)

**Priority**: High

---

## Pages Needing Custom Mobile Views (Red)

These pages require significant redesign for mobile or have complex UI that cannot be simply made responsive.

### 1. Hero Draft Page (`/herodraft/:id`)
**File**: `/frontend/app/pages/herodraft/HeroDraftPage.tsx`

**Issues**:
- Modal-based full-screen layout: `modal-box max-w-4xl`
- Top bar with two teams side-by-side assumes width
- Hero grid: `grid grid-cols-10` - 10 columns is unusable on 375px
- Choice buttons: 4 buttons in a row with `flex-1`
- Real-time draft interaction requires careful touch targets

**Reasoning for Custom Mobile View**:
The hero draft interface is a complex real-time application where both teams need to see picks/bans simultaneously. On mobile:
- Hero grid needs scrollable or filtered view
- Team information should stack vertically
- Pick/ban buttons need larger touch targets (44px minimum)
- Timer/status information needs prominent placement

**Recommendations**:
1. Create dedicated mobile hero draft component
2. Use bottom sheet pattern for hero selection
3. Swipeable team panels
4. Collapsible pick/ban rows

**Priority**: Critical

---

### 2. PlayersTab Component
**File**: `/frontend/app/pages/tournament/tabs/PlayersTab.tsx`

**Issues**:
- Search + Add button grid: `grid-cols-2` without wrapping
- User cards in responsive grid but header controls need work

**Recommendations**:
```tsx
// Header controls
<div className="flex flex-col sm:grid sm:grid-cols-2 gap-4 items-stretch">
```

**Priority**: Medium (Part of Tournament Detail)

---

### 3. TeamsTab Component
**File**: `/frontend/app/pages/tournament/tabs/TeamsTab.tsx`

**Issues**:
- Button group: `flex-col sm:flex-row` - good pattern
- Team cards grid: `grid-cols-1 lg:grid-cols-2 2xl:grid-cols-3` - good
- Overall structure is acceptable

**Recommendations**:
- Minor improvements needed
- Modal dialogs (RandomizeTeamsModal, CaptainSelectionModal, DraftModal) may need mobile treatment

**Priority**: Medium (Part of Tournament Detail)

---

### 4. GamesTab / BracketView Component
**File**: `/frontend/app/pages/tournament/tabs/GamesTab.tsx`

**Issues**:
- Tab controls + buttons may overflow
- `BracketView` component (not audited here) likely has complex bracket rendering
- Game cards grid: `grid-cols-1 md:grid-cols-2` - good

**Reasoning for Custom Mobile View**:
Tournament brackets are inherently wide, tree-based visualizations. On mobile:
- Need horizontal scroll or zoom/pan
- Consider collapsible rounds
- Match cards should be tappable with clear winner indication

**Recommendations**:
1. Add horizontal scroll wrapper to bracket
2. Consider "focused match" view for mobile
3. Use pinch-to-zoom for bracket navigation

**Priority**: High

---

### 5. LeaderboardTable Component
**File**: `/frontend/app/features/leaderboard/LeaderboardTable.tsx`

**Issues**:
- 7-column table: Rank, Player, MMR, Games, Win Rate, KDA, GPM
- No responsive breakpoints in table structure
- Table will overflow on any screen under ~700px

**Reasoning for Custom Mobile View**:
Data tables with 7+ columns cannot fit on 375px. Options:
1. **Card view**: Each player as a card with key stats
2. **Collapsible rows**: Show name + MMR, tap to expand
3. **Horizontal scroll**: Keep table but add scroll wrapper
4. **Priority columns**: Show only 3-4 columns on mobile

**Recommendations**:
```tsx
// Option 1: Card-based mobile view
{isMobile ? (
  <div className="space-y-3">
    {entries.map(entry => (
      <LeaderboardCard entry={entry} rank={index + 1} />
    ))}
  </div>
) : (
  <Table>...</Table>
)}

// Option 2: Horizontal scroll wrapper
<div className="overflow-x-auto">
  <Table className="min-w-[700px]">...</Table>
</div>
```

**Priority**: High

---

## Common Issues Summary

| Issue | Occurrences | Fix Pattern |
|-------|-------------|-------------|
| Missing `sm:` breakpoint in grids | 5 | Add `sm:grid-cols-2` before `md:` |
| Fixed widths (`w-64`, `w-32`) | 3 | Use `w-full sm:w-64` |
| Large titles without mobile size | 6 | `text-2xl sm:text-3xl` |
| `flex-row` without wrap | 4 | `flex-col sm:flex-row` |
| Header justify-between overflow | 5 | Stack on mobile with `flex-col` |
| Table overflow | 2 | Horizontal scroll or card view |
| Complex interactive UIs | 2 | Custom mobile components |

---

## Priority Action Items

### Immediate (Before Mobile Launch)
1. **Hero Draft Page** - Custom mobile view required
2. **Leaderboard Table** - Add horizontal scroll or card view
3. **Tournament Detail** - Fix title overflow, tabs
4. **TournamentTabs** - Mobile-friendly tab navigation

### Short-term (Sprint 1)
1. All pages: Add `sm:` breakpoints to grids
2. All pages: Mobile-size titles (`text-2xl sm:text-3xl`)
3. Leagues/Organizations: Filter width fix
4. Users page: Header grid fix

### Medium-term (Sprint 2)
1. Bracket View - Mobile scroll/zoom implementation
2. All modals - Ensure bottom sheet behavior on mobile
3. Touch target audit - Ensure 44px minimum for buttons

---

## Testing Recommendations

1. **Use Chrome DevTools** device emulation at 375x667 (iPhone SE)
2. **Test all interactive elements** - forms, dropdowns, modals
3. **Check horizontal overflow** - no element should cause body scroll
4. **Verify touch targets** - minimum 44x44px for buttons
5. **Test with real device** - emulation doesn't catch all issues

---

## Appendix: File Locations

| Page | Route File | Component File |
|------|-----------|----------------|
| Home | `/app/routes/home.tsx` | `/app/pages/home/home.tsx` |
| About | `/app/routes/about.tsx` | `/app/pages/about/about.tsx` |
| Tournaments | `/app/routes/tournaments.tsx` | `/app/pages/tournaments/tournaments.tsx` |
| Tournament Detail | `/app/routes/tournament.tsx` | `/app/pages/tournament/TournamentDetailPage.tsx` |
| Leagues | `/app/routes/leagues.tsx` | (inline) |
| League Detail | `/app/routes/league.tsx` | (inline) |
| Organizations | `/app/routes/organizations.tsx` | (inline) |
| Organization Detail | `/app/routes/organization.tsx` | (inline) |
| Users | `/app/routes/users.tsx` | `/app/pages/users/users.tsx` |
| User Detail | `/app/routes/user.tsx` | `/app/pages/user/user.tsx` |
| Profile | `/app/routes/profile.tsx` | `/app/pages/profile/profile.tsx` |
| Hero Draft | `/app/routes/herodraft.tsx` | `/app/pages/herodraft/HeroDraftPage.tsx` |
| Leaderboard | `/app/routes/leaderboard.tsx` | `/app/features/leaderboard/LeaderboardPage.tsx` |
| Blog | `/app/routes/blog.tsx` | `/app/pages/blog/blog.tsx` |
| Login | `/app/routes/login.tsx` | `/app/pages/home/home.tsx` |
| Redirects | `/app/routes/doneRedirect.tsx`, `/app/routes/logoutRedirect.tsx` | (redirect only) |
