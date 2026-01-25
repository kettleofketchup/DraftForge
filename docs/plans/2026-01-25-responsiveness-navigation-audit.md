# Navigation and Tab Patterns Audit

**Date**: 2026-01-25
**Working Directory**: `/home/kettle/git_repos/website/.worktrees/responsiveness`
**Purpose**: Audit all navigation and tab patterns in the frontend for mobile responsiveness

---

## Executive Summary

The frontend uses a mix of navigation patterns with varying levels of mobile responsiveness. Key findings:

1. **Main Navbar**: Uses icon-only display on mobile with `hideTextOnSmall` pattern - good but no hamburger menu
2. **Tabs**: Multiple implementations with inconsistent mobile handling - most will overflow on 375px
3. **Dropdowns**: Standard Radix UI dropdowns - work well on mobile
4. **No Sheet/Drawer component**: Missing for mobile navigation patterns
5. **No horizontal scroll for tabs**: Tabs overflow without scrolling on mobile

---

## 1. Current Navigation Patterns Found

### 1.1 Main Navigation Bar

**File**: `/home/kettle/git_repos/website/.worktrees/responsiveness/frontend/app/components/navbar/navbar.tsx`

```tsx
// Current implementation - NavItem with hideTextOnSmall pattern
const NavItem = React.forwardRef<HTMLAnchorElement, NavItemProps>(
  ({ className, icon, title, subtitle, badge, asChild = false, hideTextOnSmall = false, showSubtitleTooltip = false, ...props }, ref) => {
    // ...
    <div className={cn(
      'flex min-w-0 items-center xl:flex-col xl:items-center',
      hideTextOnSmall && 'hidden lg:flex'  // Text hidden below lg breakpoint
    )}>
      <span className="text-xs font-bold leading-normal truncate text-center text-outline-sm">{title}</span>
      {subtitle && (
        <span className="text-[10px] text-text-muted leading-normal truncate hidden xl:block text-center">
          {subtitle}
        </span>
      )}
    </div>
```

**Mobile Behavior (375px)**:
- Icons remain visible
- Text labels hidden below `lg` (1024px)
- Subtitles hidden below `xl` (1280px)
- Navigation items wrap if too many
- **Issue**: No hamburger menu for overflow - all items crammed horizontally

**Current nav structure**:
```tsx
<nav className="sticky z-50 top-0 navbar bg-base-600 shadow-elevated border-b border-border p-0">
  <div className="navbar-start flex-1">
    <SiteLogo />
    <NavLinks />  {/* About, Tournaments, Users, Organizations, Leagues, Admin */}
  </div>
  <div className="navbar-end">
    <ExternalLinks />  {/* GitHub, Docs, Bug Report */}
    <LoginWithDiscordButton />
  </div>
</nav>
```

### 1.2 Tournament Detail Tabs

**File**: `/home/kettle/git_repos/website/.worktrees/responsiveness/frontend/app/pages/tournament/tabs/TournamentTabs.tsx`

```tsx
<Tabs
  value={activeTab}
  onValueChange={setActiveTab}
  className="flex justify-center rounded-full align-middle gap-4 sm:-p1 sm:gap-2 sm:w-full"
>
  <TabsList
    className="container content-center flex w-full justify-center gap-2 rounded-full"
    data-testid="tournamentTabsList"
  >
    <TabsTrigger className="w-full active:p-1" value="players">
      Players ({playerCount})
    </TabsTrigger>
    <TabsTrigger className="w-full" value="teams">
      Teams ({teamCount})
    </TabsTrigger>
    <TabsTrigger value="bracket">
      Bracket ({gameCount})
    </TabsTrigger>
  </TabsList>
```

**Mobile Behavior (375px)**:
- Tabs are `w-full` - should stretch to fill container
- Text may truncate with counts like "Players (25)"
- **Issue**: No horizontal scrolling if content overflows
- **Issue**: Inconsistent `w-full` - first two tabs have it, third does not

### 1.3 League Detail Tabs

**File**: `/home/kettle/git_repos/website/.worktrees/responsiveness/frontend/app/components/league/LeagueTabs.tsx`

```tsx
<Tabs value={activeTab} onValueChange={onTabChange} className="w-full">
  <TabsList className="grid w-full grid-cols-3">
    <TabsTrigger value="info">Info</TabsTrigger>
    <TabsTrigger value="tournaments">Tournaments ({tournaments.length})</TabsTrigger>
    <TabsTrigger value="matches">Matches</TabsTrigger>
  </TabsList>
```

**Mobile Behavior (375px)**:
- Uses `grid grid-cols-3` - equal width columns
- Better than flex for equal sizing
- **Issue**: "Tournaments (25)" label may truncate or overflow
- **Issue**: No responsive breakpoint - same 3 columns on all sizes

### 1.4 Games Tab View Mode Tabs (Nested)

**File**: `/home/kettle/git_repos/website/.worktrees/responsiveness/frontend/app/pages/tournament/tabs/GamesTab.tsx`

```tsx
<Tabs value={viewMode} onValueChange={(v) => setViewMode(v as 'bracket' | 'list')}>
  <div className="flex items-center justify-between mb-4">
    <TabsList>
      <TabsTrigger value="bracket">Bracket View</TabsTrigger>
      <TabsTrigger value="list">List View</TabsTrigger>
    </TabsList>
    {/* Action buttons */}
  </div>
```

**Mobile Behavior (375px)**:
- Simple 2-tab layout - fits well
- Uses default TabsList styling (`w-fit`)
- Action buttons may push tabs off-screen

### 1.5 Dropdown Menus

**File**: `/home/kettle/git_repos/website/.worktrees/responsiveness/frontend/app/components/ui/dropdown-menu.tsx`

Standard Radix UI dropdown implementation with proper portal rendering.

**Usage locations**:
- Profile menu (`login.tsx`)
- Bracket toolbar (`BracketToolbar.tsx`)
- Active draft banner (`ActiveDraftBanner.tsx`)
- Add player dropdown (`addPlayerDropdown.tsx`)

**Mobile Behavior (375px)**:
- Works well - portals to body
- Uses `max-h-[var(--radix-dropdown-menu-content-available-height)]` for viewport-aware height
- **Good**: Scrollable when content exceeds viewport

### 1.6 User Profile Dropdown

**File**: `/home/kettle/git_repos/website/.worktrees/responsiveness/frontend/app/components/navbar/login.tsx`

```tsx
<DropdownMenu>
  <DropdownMenuTrigger>
    <div className="m-0 btn-circle avatar flex p-0 relative">
      <AvatarContainer>
        <UserAvatarImg user={currentUser} />
      </AvatarContainer>
      <DraftNotificationBadge />
    </div>
  </DropdownMenuTrigger>
  <DropdownMenuContent>
    <DropdownMenuLabel>
      <a href="/profile">
        <Button><UserPenIcon />Profile</Button>
      </a>
    </DropdownMenuLabel>
    <DropdownMenuSeparator />
    <DropdownMenuItem>
      <Button onClick={logoutClick} variant={'destructive'}>
        <LogOutIcon />Logout
      </Button>
    </DropdownMenuItem>
  </DropdownMenuContent>
</DropdownMenu>
```

**Mobile Behavior (375px)**:
- Avatar button works well as touch target
- **Issue**: Button inside DropdownMenuItem - unusual pattern, may cause click handling issues

---

## 2. Mobile Responsiveness Analysis (375px)

### 2.1 Main Navbar at 375px

| Element | Current Behavior | Issue |
|---------|------------------|-------|
| Logo | 40x40px fixed | Good |
| Nav Items | Icons only (text hidden) | Text hidden below lg (1024px) |
| Gap between items | `gap-0.5 lg:gap-1` | Compressed on mobile |
| External links | Icons only | Same pattern as nav items |
| Login button | Full button with text | May overflow |

**Calculated width at 375px**:
- Logo: ~56px (40px + padding)
- 6 Nav items: ~6 x 40px = 240px (icons + minimal padding)
- 3 External links: ~3 x 40px = 120px
- Login button: ~80-100px
- **Total**: ~496-516px - **OVERFLOWS 375px viewport**

### 2.2 Tournament Tabs at 375px

| Tab | Content | Est. Width |
|-----|---------|------------|
| Players | "Players (25)" | ~90px |
| Teams | "Teams (10)" | ~80px |
| Bracket | "Bracket (15)" | ~95px |
| **Total** | | ~265px + padding |

With container padding (~24px each side), content area is ~327px.
**Should fit**, but counts could push over limit.

### 2.3 League Tabs at 375px

Using `grid-cols-3` on ~327px content area:
- Each cell: ~109px
- "Tournaments (25)": likely truncates

### 2.4 What's Missing for Mobile

1. **Hamburger Menu**: No mobile nav drawer/sheet for main navigation
2. **Horizontal Tab Scrolling**: No `overflow-x-auto` on TabsList components
3. **Sheet Component**: Not installed in UI components
4. **Responsive Tab Layout**: No vertical tabs option for mobile
5. **Safe Area Handling**: No padding for notched devices

---

## 3. Inconsistencies Identified

### 3.1 Tab Styling Inconsistencies

| Location | TabsList className | Issue |
|----------|-------------------|-------|
| TournamentTabs | `container content-center flex w-full justify-center gap-2 rounded-full` | Uses container + flex |
| LeagueTabs | `grid w-full grid-cols-3` | Uses grid |
| GamesTab | (default) | No custom styling |

### 3.2 TabsTrigger Width Inconsistencies

```tsx
// TournamentTabs - inconsistent
<TabsTrigger className="w-full active:p-1" value="players">  // has w-full
<TabsTrigger className="w-full" value="teams">               // has w-full
<TabsTrigger value="bracket">                                 // NO w-full

// LeagueTabs - consistent
// All triggers inherit from grid-cols-3 parent
```

### 3.3 NavItem Pattern Inconsistencies

```tsx
// Some items have showSubtitleTooltip
<NavItem
  href={DOCS_URL}
  icon={<DocsIcon />}
  title="Docs"
  subtitle="Secret Sauce"
  showSubtitleTooltip  // Has tooltip
/>

// Others don't
<NavItem
  href="/tournaments"
  icon={<TrophyIcon />}
  title="Tournaments"
  subtitle="Compete & win"
  // No tooltip - subtitle just hidden
/>
```

### 3.4 Mixed Component Libraries

- **Radix UI**: Tabs, DropdownMenu, Dialog
- **HeadlessUI**: Combobox (in addPlayerDropdown.tsx)
- **DaisyUI classes**: `collapse`, `alert`, `btn-circle`, `avatar`, `input`, `select`

---

## 4. Recommendations

### 4.1 Responsive Tab Component

Create a custom wrapper component that handles mobile responsiveness:

```tsx
// components/custom/responsive-tabs.tsx
import { Tabs, TabsList, TabsTrigger, TabsContent } from '~/components/ui/tabs';
import { ScrollArea, ScrollBar } from '~/components/ui/scroll-area';
import { cn } from '~/lib/utils';

interface ResponsiveTabsProps {
  tabs: Array<{
    value: string;
    label: string;
    badge?: number;
    icon?: React.ReactNode;
  }>;
  value: string;
  onValueChange: (value: string) => void;
  children: React.ReactNode;
  className?: string;
}

export function ResponsiveTabs({
  tabs,
  value,
  onValueChange,
  children,
  className
}: ResponsiveTabsProps) {
  return (
    <Tabs value={value} onValueChange={onValueChange} className={cn("w-full", className)}>
      {/* Horizontal scroll wrapper for mobile */}
      <ScrollArea className="w-full">
        <TabsList className="inline-flex w-full min-w-max sm:grid sm:grid-cols-auto-fit gap-1 p-1">
          {tabs.map((tab) => (
            <TabsTrigger
              key={tab.value}
              value={tab.value}
              className="flex-shrink-0 gap-1.5 min-w-[80px] sm:flex-1"
            >
              {tab.icon}
              <span className="truncate">{tab.label}</span>
              {tab.badge !== undefined && (
                <span className="text-xs opacity-70">({tab.badge})</span>
              )}
            </TabsTrigger>
          ))}
        </TabsList>
        <ScrollBar orientation="horizontal" className="h-1.5" />
      </ScrollArea>
      {children}
    </Tabs>
  );
}
```

**Usage**:
```tsx
<ResponsiveTabs
  tabs={[
    { value: 'players', label: 'Players', badge: playerCount },
    { value: 'teams', label: 'Teams', badge: teamCount },
    { value: 'bracket', label: 'Bracket', badge: gameCount },
  ]}
  value={activeTab}
  onValueChange={setActiveTab}
>
  <TabsContent value="players"><PlayersTab /></TabsContent>
  <TabsContent value="teams"><TeamsTab /></TabsContent>
  <TabsContent value="bracket"><GamesTab /></TabsContent>
</ResponsiveTabs>
```

### 4.2 Mobile Navigation Sheet

Add shadcn Sheet component and create mobile nav:

```bash
npx shadcn@latest add sheet
```

```tsx
// components/custom/mobile-nav.tsx
import { Menu } from 'lucide-react';
import { Sheet, SheetContent, SheetTrigger } from '~/components/ui/sheet';
import { Button } from '~/components/ui/button';

export function MobileNav() {
  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon" className="md:hidden">
          <Menu className="h-5 w-5" />
          <span className="sr-only">Toggle menu</span>
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="w-72">
        <nav className="flex flex-col gap-4 mt-8">
          <a href="/about" className="flex items-center gap-3 p-2 hover:bg-muted rounded-md">
            <AboutIcon />
            <span>About</span>
          </a>
          <a href="/tournaments" className="flex items-center gap-3 p-2 hover:bg-muted rounded-md">
            <TrophyIcon />
            <span>Tournaments</span>
          </a>
          {/* ... other nav items */}
        </nav>
      </SheetContent>
    </Sheet>
  );
}
```

Update navbar:
```tsx
export const ResponsiveAppBar: React.FC = memo(() => {
  return (
    <header>
      <nav className="sticky z-50 top-0 navbar bg-base-600 ...">
        <div className="navbar-start flex-1">
          <MobileNav />  {/* Add hamburger for mobile */}
          <SiteLogo />
          <NavLinks className="hidden md:flex" />  {/* Hide on mobile */}
        </div>
        <div className="navbar-end">
          <ExternalLinks className="hidden lg:flex" />  {/* Hide on mobile */}
          <LoginWithDiscordButton />
        </div>
      </nav>
    </header>
  );
});
```

### 4.3 Consistent Tab Styling

Create a standardized TabsList wrapper:

```tsx
// components/custom/app-tabs-list.tsx
import { TabsList } from '~/components/ui/tabs';
import { cn } from '~/lib/utils';

interface AppTabsListProps {
  children: React.ReactNode;
  className?: string;
  columns?: number;  // For grid layout
  stretch?: boolean; // Full width triggers
}

export function AppTabsList({
  children,
  className,
  columns,
  stretch = true
}: AppTabsListProps) {
  return (
    <TabsList
      className={cn(
        "w-full",
        columns ? `grid grid-cols-${columns}` : "flex",
        stretch && "justify-stretch",
        className
      )}
    >
      {children}
    </TabsList>
  );
}
```

### 4.4 Scrollable Tab List Pattern

For tabs that may overflow:

```tsx
// components/custom/scrollable-tabs-list.tsx
import { TabsList } from '~/components/ui/tabs';
import { ScrollArea, ScrollBar } from '~/components/ui/scroll-area';
import { cn } from '~/lib/utils';

interface ScrollableTabsListProps {
  children: React.ReactNode;
  className?: string;
}

export function ScrollableTabsList({ children, className }: ScrollableTabsListProps) {
  return (
    <ScrollArea className="w-full whitespace-nowrap">
      <TabsList className={cn("inline-flex w-max gap-1", className)}>
        {children}
      </TabsList>
      <ScrollBar orientation="horizontal" />
    </ScrollArea>
  );
}
```

### 4.5 Touch-Friendly Improvements

Update TabsTrigger base styles for better mobile UX:

```tsx
// components/ui/tabs.tsx - update TabsTrigger
function TabsTrigger({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      data-slot="tabs-trigger"
      className={cn(
        // Existing classes...
        "min-h-11",  // 44px touch target
        "px-3 py-2", // More padding for touch
        "text-sm sm:text-base", // Larger text on mobile
        className
      )}
      {...props}
    />
  )
}
```

---

## 5. Implementation Priority

### High Priority
1. **Add Sheet component** - Required for mobile nav
2. **Create MobileNav** - Fix navbar overflow on 375px
3. **Add horizontal scroll to TournamentTabs** - Most used tab set

### Medium Priority
4. **Create ResponsiveTabs component** - Reusable pattern
5. **Standardize TabsList styling** - Consistency
6. **Update touch targets** - min-h-11 on triggers

### Low Priority
7. **Migrate HeadlessUI Combobox** - Use Radix Command instead
8. **Remove DaisyUI classes** - Full shadcn migration
9. **Add viewport meta improvements** - notch handling

---

## 6. Files to Modify

| File | Changes |
|------|---------|
| `components/navbar/navbar.tsx` | Add MobileNav, hide NavLinks on mobile |
| `components/ui/sheet.tsx` | Add via shadcn CLI |
| `components/custom/mobile-nav.tsx` | New component |
| `components/custom/responsive-tabs.tsx` | New component |
| `pages/tournament/tabs/TournamentTabs.tsx` | Use ResponsiveTabs |
| `components/league/LeagueTabs.tsx` | Use ResponsiveTabs |
| `pages/tournament/tabs/GamesTab.tsx` | Add scroll wrapper to nested tabs |
| `components/ui/tabs.tsx` | Update touch target sizes |

---

## 7. Testing Checklist

- [ ] Navbar at 375px - hamburger menu visible
- [ ] Navbar at 768px - hybrid (some items visible)
- [ ] Navbar at 1024px+ - full navigation
- [ ] Tournament tabs scroll horizontally on mobile
- [ ] League tabs readable on 375px
- [ ] Dropdown menus don't overflow viewport
- [ ] Profile menu accessible on mobile
- [ ] Touch targets are 44px minimum
- [ ] No horizontal page scroll from overflow

---

## Appendix: Component File Locations

```
frontend/app/
├── components/
│   ├── navbar/
│   │   ├── navbar.tsx          # Main navigation bar
│   │   ├── login.tsx           # User profile dropdown
│   │   └── index.tsx           # Exports
│   ├── ui/
│   │   ├── tabs.tsx            # Base Radix tabs
│   │   ├── dropdown-menu.tsx   # Radix dropdown
│   │   └── scroll-area.tsx     # Scroll container
│   ├── league/
│   │   └── LeagueTabs.tsx      # League detail tabs
│   ├── bracket/
│   │   └── controls/
│   │       └── BracketToolbar.tsx  # Bracket action dropdown
│   └── draft/
│       ├── ActiveDraftBanner.tsx   # Desktop banner with dropdown
│       └── FloatingDraftIndicator.tsx  # Mobile floating button
├── pages/
│   └── tournament/
│       └── tabs/
│           ├── TournamentTabs.tsx  # Main tournament tabs
│           ├── GamesTab.tsx        # Nested view mode tabs
│           ├── PlayersTab.tsx      # Player list
│           └── TeamsTab.tsx        # Team list
└── routes/
    └── league.tsx              # League page using LeagueTabs
```
