# Card Components and Data Display Audit

**Date**: 2026-01-25
**Working Directory**: `/home/kettle/git_repos/website/.worktrees/responsiveness`
**Scope**: All card components and data display patterns in `frontend/app/`

---

## Executive Summary

This audit identified **16 card-type components** across the frontend codebase with inconsistent approaches to:
- Text truncation and overflow handling
- Card structure and layout patterns
- Use of shadcn/ui primitives vs custom implementations
- Component-first design principles

**Key Finding**: The `UserCard` component has manual truncation at 8 characters for usernames/nicknames, but this approach is inconsistent with other cards that use CSS truncation or no truncation at all.

---

## 1. Card Components Inventory

### 1.1 Entity Cards (Primary Data Display)

| Component | File Path | Uses shadcn Card | Truncation Method |
|-----------|-----------|------------------|-------------------|
| UserCard | `/components/user/userCard.tsx` | No (custom) | Manual slice(0,8) |
| TeamCard | `/components/team/teamCard.tsx` | No (custom) | None |
| TournamentCard | `/components/tournament/card/TournamentCard.tsx` | No (custom) | None |
| OrganizationCard | `/components/organization/OrganizationCard.tsx` | Yes | CSS line-clamp-2 |
| LeagueCard | `/components/league/LeagueCard.tsx` | Yes | CSS line-clamp-2 |
| LeagueMatchCard | `/components/league/LeagueMatchCard.tsx` | Yes | None |
| LeagueStatsCard | `/components/user/LeagueStatsCard.tsx` | No (custom) | None |

### 1.2 Draft/Game Cards

| Component | File Path | Uses shadcn Card | Truncation Method |
|-----------|-----------|------------------|-------------------|
| DraftRoundCard | `/components/draft/roundView/draftRoundCard.tsx` | Yes | None |
| GameCard | `/components/game/gameCard/gameCard.tsx` | No (custom) | None |
| SteamMatchCard | `/components/bracket/modals/SteamMatchCard.tsx` | No (custom div) | CSS truncate max-w-[100px] |

### 1.3 Feature/About Cards

| Component | File Path | Uses shadcn Card | Truncation Method |
|-----------|-----------|------------------|-------------------|
| FeatureCard | `/pages/about/sections/FeatureCard.tsx` | No (custom) | None |

---

## 2. Detailed Analysis: UserCard

**File**: `/home/kettle/git_repos/website/.worktrees/responsiveness/frontend/app/components/user/userCard.tsx`

### Current Implementation

```tsx
// Lines 192-208 - Manual truncation pattern
{user.username && (
  <Item size="sm" variant="muted" className="!p-1">
    <ItemContent className="!gap-0">
      <ItemTitle className="!text-xs text-muted-foreground">Username</ItemTitle>
      <span className="text-sm">{user.username.length > 8 ? `${user.username.slice(0, 8)}...` : user.username}</span>
    </ItemContent>
  </Item>
)}
{user.nickname && user.nickname !== user.username && (
  <Item size="sm" variant="muted" className="!p-1">
    <ItemContent className="!gap-0">
      <ItemTitle className="!text-xs text-muted-foreground">Nickname</ItemTitle>
      <span className="text-sm">{user.nickname.length > 8 ? `${user.nickname.slice(0, 8)}...` : user.nickname}</span>
    </ItemContent>
  </Item>
)}
{user.steamid && (
  <Item size="sm" variant="muted" className="!p-1">
    <ItemContent className="!gap-0">
      <ItemTitle className="!text-xs text-muted-foreground">Steam ID</ItemTitle>
      <span className="text-sm">{String(user.steamid).length > 8 ? `${String(user.steamid).slice(0, 8)}...` : user.steamid}</span>
    </ItemContent>
  </Item>
)}
```

### Issues Identified

1. **Hardcoded truncation length** (8 characters) - not responsive
2. **Manual string manipulation** instead of CSS utilities
3. **Inconsistent with header** which uses CSS `truncate` class
4. **No tooltip** for showing full text on hover
5. **Does NOT use shadcn Card** - uses custom `bg-base-300 card` classes
6. **Uses Item component** from shadcn with override classes (`!p-1`, `!gap-0`)

### Header Section (Lines 132-136)

```tsx
<h2 className="card-title text-base truncate">
  {user.nickname || user.username}
</h2>
```

This uses CSS truncation properly, but the data fields below use manual slicing.

---

## 3. Text Truncation Analysis

### Components WITH Proper Truncation

| Component | Method | Max Width | Notes |
|-----------|--------|-----------|-------|
| OrganizationCard | `line-clamp-2` | None | Description only |
| LeagueCard | `line-clamp-2` | None | Description only |
| SteamMatchCard | `truncate max-w-[100px]` | 100px | Player names |
| DraftTopBar | `truncate max-w-[40px] sm:max-w-[56px]` | Responsive | Player names |
| MatchNode | `truncate min-w-[60px] max-w-[120px]` | 60-120px | Team names |
| HeroDraftHistoryModal | `truncate` | None | Hero/player names |

### Components WITHOUT Truncation

| Component | Issue | Affected Fields |
|-----------|-------|-----------------|
| TeamCard | No truncation | Team name, member names |
| TournamentCard | No truncation | Tournament name |
| DraftRoundCard | No truncation | Captain name |
| GameCard | No truncation | Team/captain names |
| LeagueMatchCard | No truncation | Captain names |
| LeagueStatsCard | No truncation | Stat labels |

### Components with Manual Truncation (Anti-Pattern)

| Component | Pattern | Length |
|-----------|---------|--------|
| UserCard | `slice(0, 8) + '...'` | 8 chars |

---

## 4. Card Styling Patterns

### Pattern A: DaisyUI Custom Cards (Legacy)

Used by: UserCard, TeamCard, TournamentCard, GameCard, FeatureCard

```tsx
<div className="card bg-base-300 shadow-elevated w-full
  hover:bg-base-200 focus:outline-2
  focus:outline-offset-2 focus:outline-primary
  active:bg-base-200 transition-all duration-300 ease-in-out">
```

### Pattern B: shadcn Card (Modern)

Used by: OrganizationCard, LeagueCard, LeagueMatchCard, DraftRoundCard

```tsx
<Card className="hover:bg-accent transition-colors cursor-pointer">
  <CardHeader>
    <CardTitle>...</CardTitle>
    <CardDescription>...</CardDescription>
  </CardHeader>
  <CardContent>...</CardContent>
</Card>
```

### Pattern C: Custom Div with Border (Minimal)

Used by: SteamMatchCard, LeagueStatsCard

```tsx
<div className="border rounded-lg p-4">
  ...
</div>
```

---

## 5. Recommendations

### 5.1 Create UserCardText Component

A reusable component for title + value display with consistent truncation.

**Proposed Location**: `/frontend/app/components/custom/UserCardText.tsx`

```tsx
import { cn } from "~/lib/utils";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "~/components/ui/tooltip";

interface UserCardTextProps {
  title: string;
  value: string | number | null | undefined;
  /** Maximum characters before truncation (default: 12) */
  maxChars?: number;
  /** Show tooltip with full value when truncated */
  showTooltip?: boolean;
  className?: string;
}

export function UserCardText({
  title,
  value,
  maxChars = 12,
  showTooltip = true,
  className,
}: UserCardTextProps) {
  if (value === null || value === undefined) return null;

  const stringValue = String(value);
  const isTruncated = stringValue.length > maxChars;
  const displayValue = isTruncated
    ? `${stringValue.slice(0, maxChars)}...`
    : stringValue;

  const content = (
    <div className={cn("flex flex-col gap-0", className)}>
      <span className="text-xs text-muted-foreground">{title}</span>
      <span className="text-sm font-medium truncate">{displayValue}</span>
    </div>
  );

  if (showTooltip && isTruncated) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          {content}
        </TooltipTrigger>
        <TooltipContent>
          <p>{stringValue}</p>
        </TooltipContent>
      </Tooltip>
    );
  }

  return content;
}
```

### 5.2 Standardized Card Layouts

Create wrapper components that enforce consistent styling:

**Proposed Location**: `/frontend/app/components/custom/EntityCard.tsx`

```tsx
import { cn } from "~/lib/utils";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "~/components/ui/card";

interface EntityCardProps {
  children: React.ReactNode;
  className?: string;
  onClick?: () => void;
  variant?: "default" | "interactive";
}

export function EntityCard({
  children,
  className,
  onClick,
  variant = "default",
}: EntityCardProps) {
  return (
    <Card
      className={cn(
        "transition-all duration-200",
        variant === "interactive" && [
          "cursor-pointer",
          "hover:bg-accent/50",
          "hover:shadow-md",
          "active:scale-[0.98]",
        ],
        className
      )}
      onClick={onClick}
    >
      {children}
    </Card>
  );
}

// Convenience exports
export { CardContent, CardHeader, CardTitle, CardDescription };
```

### 5.3 Truncation Utility Functions

**Proposed Location**: Add to `/frontend/app/lib/utils.ts`

```tsx
/**
 * Truncate text with ellipsis
 * @param text - Text to truncate
 * @param maxLength - Maximum length before truncation
 * @returns Truncated text with ellipsis if needed
 */
export function truncateText(text: string | null | undefined, maxLength: number = 12): string {
  if (!text) return "";
  return text.length > maxLength ? `${text.slice(0, maxLength)}...` : text;
}

/**
 * Check if text will be truncated
 */
export function willTruncate(text: string | null | undefined, maxLength: number = 12): boolean {
  return !!text && text.length > maxLength;
}
```

### 5.4 Migration Priority

1. **HIGH**: UserCard - currently hardcoded, most visible component
2. **HIGH**: Create UserCardText component for reuse
3. **MEDIUM**: TeamCard - no truncation at all
4. **MEDIUM**: TournamentCard - no truncation at all
5. **LOW**: Migrate remaining cards to shadcn Card base

### 5.5 Responsive Truncation Guidelines

| Breakpoint | Max Chars | Use Case |
|------------|-----------|----------|
| mobile (< 640px) | 8-10 | Compact views, grids |
| tablet (640-1024px) | 12-16 | Standard cards |
| desktop (> 1024px) | 16-24 | Full displays |

**CSS Alternative** (preferred for dynamic widths):

```tsx
<span className="truncate max-w-[80px] sm:max-w-[120px] lg:max-w-[200px]">
  {value}
</span>
```

---

## 6. Immediate Action Items

### For UserCard Specifically

1. Replace manual `slice(0, 8)` with `UserCardText` component
2. Increase default truncation to 12 characters (better UX)
3. Add tooltips for truncated values
4. Consider migrating to shadcn Card base

### Current UserCard Code to Replace:

```tsx
// BEFORE (lines 189-211)
{user.username && (
  <Item size="sm" variant="muted" className="!p-1">
    <ItemContent className="!gap-0">
      <ItemTitle className="!text-xs text-muted-foreground">Username</ItemTitle>
      <span className="text-sm">{user.username.length > 8 ? `${user.username.slice(0, 8)}...` : user.username}</span>
    </ItemContent>
  </Item>
)}

// AFTER (using proposed component)
{user.username && (
  <Item size="sm" variant="muted" className="!p-1">
    <ItemContent className="!gap-0">
      <UserCardText title="Username" value={user.username} maxChars={12} />
    </ItemContent>
  </Item>
)}
```

---

## 7. Files Referenced

| File Path | Lines | Notes |
|-----------|-------|-------|
| `/frontend/app/components/user/userCard.tsx` | 1-245 | Main UserCard component |
| `/frontend/app/components/team/teamCard.tsx` | 1-123 | TeamCard component |
| `/frontend/app/components/tournament/card/TournamentCard.tsx` | 1-319 | TournamentCard component |
| `/frontend/app/components/organization/OrganizationCard.tsx` | 1-51 | OrganizationCard (uses shadcn) |
| `/frontend/app/components/league/LeagueCard.tsx` | 1-45 | LeagueCard (uses shadcn) |
| `/frontend/app/components/league/LeagueMatchCard.tsx` | 1-181 | LeagueMatchCard component |
| `/frontend/app/components/user/LeagueStatsCard.tsx` | 1-135 | Stats display card |
| `/frontend/app/components/draft/roundView/draftRoundCard.tsx` | 1-72 | Draft round display |
| `/frontend/app/components/game/gameCard/gameCard.tsx` | 1-226 | Game card component |
| `/frontend/app/components/bracket/modals/SteamMatchCard.tsx` | 1-179 | Steam match display |
| `/frontend/app/pages/about/sections/FeatureCard.tsx` | 1-33 | Feature display card |
| `/frontend/app/components/ui/card.tsx` | 1-93 | shadcn Card primitives |
| `/frontend/app/components/ui/item.tsx` | 1-194 | Item component (used by UserCard) |
| `/frontend/app/lib/utils.ts` | 1-7 | Utility functions |

---

## 8. Summary

The codebase has evolved organically, resulting in three distinct card patterns:

1. **Legacy DaisyUI cards** - Custom styling, inconsistent truncation
2. **Modern shadcn cards** - Proper structure, CSS-based truncation
3. **Minimal custom cards** - Ad-hoc implementations

**Recommended Path Forward**:

1. Create `UserCardText` component for immediate UserCard improvements
2. Create `EntityCard` wrapper for consistent new card development
3. Add truncation utilities to `lib/utils.ts`
4. Gradually migrate legacy cards to shadcn-based patterns
5. Standardize on CSS truncation over manual string slicing
