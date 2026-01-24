# Active Draft Context Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace polling endpoint with active_drafts in current_user response; add banner UI for draft notifications.

**Architecture:** Backend adds `active_drafts` array to current_user response by querying DraftRound (team drafts) and HeroDraft (hero drafts). Frontend removes polling hook, reads from user store, displays banner below navbar.

**Tech Stack:** Django REST Framework, React, Zustand, TypeScript, Tailwind CSS

---

## Task 1: Backend - Add active_drafts to current_user

**Files:**
- Modify: `backend/app/views_main.py:518-529` (current_user function)

**Step 1: Update current_user to include active_drafts**

Replace the `current_user` function at line 518-529:

```python
@api_view(["GET"])
@permission_classes((AllowAny,))
def current_user(request):
    user = request.user
    if request.user.is_authenticated:
        data = UserSerializer(user).data

        # Add active drafts info
        active_drafts = []

        # Team drafts: user is captain with pending pick in in_progress tournament
        from app.models import DraftRound, HeroDraft, DraftTeam

        pending_team_round = (
            DraftRound.objects.filter(
                captain=user,
                choice__isnull=True,
                draft__tournament__state="in_progress",
            )
            .select_related("draft__tournament")
            .order_by("pick_number")
            .first()
        )

        if pending_team_round:
            active_drafts.append({
                "type": "team_draft",
                "tournament_pk": pending_team_round.draft.tournament.pk,
                "draft_state": pending_team_round.draft.tournament.state,
            })

        # Hero drafts: user is captain of a DraftTeam in an active HeroDraft
        active_hero_states = ["waiting_for_captains", "rolling", "choosing", "drafting"]
        hero_draft_teams = DraftTeam.objects.filter(
            tournament_team__captain=user,
            draft__state__in=active_hero_states,
        ).select_related("draft__game__tournament")

        for draft_team in hero_draft_teams:
            hero_draft = draft_team.draft
            active_drafts.append({
                "type": "hero_draft",
                "tournament_pk": hero_draft.game.tournament.pk,
                "game_pk": hero_draft.game.pk,
                "herodraft_pk": hero_draft.pk,
                "draft_state": hero_draft.state,
            })

        data["active_drafts"] = active_drafts
        return Response(data, 201)
    else:
        return Response()
```

**Step 2: Verify the change**

Run: `cd /home/kettle/git_repos/website/.worktrees/herodraft && source .venv/bin/activate && inv test.run --cmd 'python manage.py check'`
Expected: System check identified no issues.

**Step 3: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft && git add backend/app/views_main.py && git commit -m "feat(backend): add active_drafts to current_user response"
```

---

## Task 2: Backend - Remove get_active_draft_for_user endpoint

**Files:**
- Modify: `backend/app/functions/tournament.py` (remove function at lines 464-505)
- Modify: `backend/backend/urls.py` (remove route)

**Step 1: Remove the function from tournament.py**

Delete lines 464-505 (the `get_active_draft_for_user` function) from `backend/app/functions/tournament.py`.

**Step 2: Remove the import and URL route from urls.py**

In `backend/backend/urls.py`:

Remove from imports (line 27):
```python
    get_active_draft_for_user,
```

Remove from urlpatterns (lines 122-126):
```python
    path(
        "api/active-draft-for-user/",
        get_active_draft_for_user,
        name="active-draft-for-user",
    ),
```

**Step 3: Verify the change**

Run: `cd /home/kettle/git_repos/website/.worktrees/herodraft && source .venv/bin/activate && inv test.run --cmd 'python manage.py check'`
Expected: System check identified no issues.

**Step 4: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft && git add backend/app/functions/tournament.py backend/backend/urls.py && git commit -m "feat(backend): remove deprecated active-draft-for-user endpoint"
```

---

## Task 3: Frontend - Update UserSchema to include active_drafts

**Files:**
- Modify: `frontend/app/components/user/schemas.ts`

**Step 1: Add ActiveDraftSchema and update UserSchema**

Update `frontend/app/components/user/schemas.ts`:

```typescript
import { z } from 'zod';

export const PositionSchema = z.object({
  pk: z.number().optional(),
  carry: z.number().min(0, { message: 'Carry position must be selected.' }),
  mid: z.number().min(0, { message: 'Mid position must be selected.' }),
  offlane: z.number().min(0, { message: 'Offlane position must be selected.' }),
  soft_support: z
    .number()
    .min(0, { message: 'Soft Support position must be selected.' }),
  hard_support: z
    .number()
    .min(0, { message: 'Hard Support position must be selected.' }),
});

export const ActiveDraftSchema = z.discriminatedUnion('type', [
  z.object({
    type: z.literal('team_draft'),
    tournament_pk: z.number(),
    draft_state: z.string(),
  }),
  z.object({
    type: z.literal('hero_draft'),
    tournament_pk: z.number(),
    game_pk: z.number(),
    herodraft_pk: z.number(),
    draft_state: z.string(),
  }),
]);

export type ActiveDraftType = z.infer<typeof ActiveDraftSchema>;

export const UserSchema = z.object({
  positions: PositionSchema.optional(),
  username: z.string().min(2).max(100),
  avatarUrl: z.string().url().optional(),
  is_staff: z.boolean().optional(),
  is_superuser: z.boolean().optional(),
  nickname: z.string().min(2).max(100).nullable().optional(),
  mmr: z.number().min(0).nullable().optional(),
  steamid: z.number().min(0).nullable().optional(),
  avatar: z.string().url().nullable().optional(),
  pk: z.number().min(0).optional(),
  discordNickname: z.string().min(2).max(100).nullable().optional(),
  discordId: z.string().min(2).max(100).nullable().optional(),
  guildNickname: z.string().min(2).max(100).nullable().optional().optional(),
  active_drafts: z.array(ActiveDraftSchema).optional(),
});
```

**Step 2: Export the new type from user index**

Check if `frontend/app/components/user/index.tsx` re-exports schemas. If needed, add export for `ActiveDraftType`.

**Step 3: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft && git add frontend/app/components/user/schemas.ts && git commit -m "feat(frontend): add ActiveDraftSchema to user types"
```

---

## Task 4: Frontend - Delete useActiveDraft hook

**Files:**
- Delete: `frontend/app/hooks/useActiveDraft.ts`

**Step 1: Delete the file**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft && rm frontend/app/hooks/useActiveDraft.ts
```

**Step 2: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft && git add -A && git commit -m "feat(frontend): remove polling useActiveDraft hook"
```

---

## Task 5: Frontend - Update DraftNotificationBadge

**Files:**
- Modify: `frontend/app/components/draft/DraftNotificationBadge.tsx`

**Step 1: Update to use userStore instead of useActiveDraft**

Replace contents of `frontend/app/components/draft/DraftNotificationBadge.tsx`:

```tsx
import { motion } from 'framer-motion';
import { useUserStore } from '~/store/userStore';

/**
 * Flashing notification badge shown when user has active drafts.
 *
 * Displays as a small red dot that pulses/flashes to draw attention.
 * Should be positioned absolutely within a relative parent (e.g., user avatar).
 */
export const DraftNotificationBadge: React.FC = () => {
  const activeDrafts = useUserStore(
    (state) => state.currentUser?.active_drafts,
  );

  if (!activeDrafts || activeDrafts.length === 0) {
    return null;
  }

  return (
    <motion.div
      data-testid="draft-notification-badge"
      className="absolute -top-1 -right-1 w-4 h-4 bg-red-500 rounded-full border-2 border-white shadow-md"
      animate={{
        scale: [1, 1.2, 1],
        opacity: [1, 0.7, 1],
      }}
      transition={{
        duration: 1,
        repeat: Infinity,
        ease: 'easeInOut',
      }}
      aria-label="You have active drafts"
      role="status"
    />
  );
};
```

**Step 2: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft && git add frontend/app/components/draft/DraftNotificationBadge.tsx && git commit -m "feat(frontend): update DraftNotificationBadge to use userStore"
```

---

## Task 6: Frontend - Update FloatingDraftIndicator

**Files:**
- Modify: `frontend/app/components/draft/FloatingDraftIndicator.tsx`

**Step 1: Update to use userStore and show first active draft**

Replace contents of `frontend/app/components/draft/FloatingDraftIndicator.tsx`:

```tsx
import { motion } from 'framer-motion';
import { ClipboardPen } from 'lucide-react';
import { useUserStore } from '~/store/userStore';
import type { ActiveDraftType } from '~/components/user/schemas';

/**
 * Build the URL for navigating to an active draft.
 */
function getDraftUrl(draft: ActiveDraftType): string {
  if (draft.type === 'team_draft') {
    return `/tournament/${draft.tournament_pk}/teams/draft`;
  }
  return `/tournament/${draft.tournament_pk}/bracket/draft/${draft.herodraft_pk}`;
}

/**
 * Floating indicator shown at bottom-right of screen when user has active drafts.
 * For mobile usage - provides a prominent, always-visible notification.
 */
export const FloatingDraftIndicator: React.FC = () => {
  const activeDrafts = useUserStore(
    (state) => state.currentUser?.active_drafts,
  );

  if (!activeDrafts || activeDrafts.length === 0) {
    return null;
  }

  // Show first draft for mobile floating indicator
  const firstDraft = activeDrafts[0];
  const draftLabel =
    firstDraft.type === 'team_draft' ? 'Team Draft' : 'Hero Draft';

  return (
    <motion.a
      data-testid="floating-draft-indicator"
      href={getDraftUrl(firstDraft)}
      className="fixed bottom-6 right-6 z-50 bg-red-600 hover:bg-red-700
                 text-white px-4 py-3 rounded-full shadow-lg
                 flex items-center gap-2 cursor-pointer
                 transition-colors duration-200 md:hidden"
      animate={{
        scale: [1, 1.05, 1],
      }}
      transition={{
        duration: 1.5,
        repeat: Infinity,
        ease: 'easeInOut',
      }}
      aria-label={`Active ${draftLabel}`}
      role="alert"
    >
      <ClipboardPen className="w-5 h-5" />
      <span className="font-medium">
        {activeDrafts.length > 1
          ? `${activeDrafts.length} Active Drafts`
          : `Active ${draftLabel}`}
      </span>
    </motion.a>
  );
};
```

**Step 2: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft && git add frontend/app/components/draft/FloatingDraftIndicator.tsx && git commit -m "feat(frontend): update FloatingDraftIndicator to use userStore"
```

---

## Task 7: Frontend - Create ActiveDraftBanner component

**Files:**
- Create: `frontend/app/components/draft/ActiveDraftBanner.tsx`

**Step 1: Create the banner component**

Create `frontend/app/components/draft/ActiveDraftBanner.tsx`:

```tsx
import { ChevronDown, ClipboardPen, X } from 'lucide-react';
import { useState } from 'react';
import { useLocation } from 'react-router';
import { Button } from '~/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '~/components/ui/dropdown-menu';
import { useUserStore } from '~/store/userStore';
import type { ActiveDraftType } from '~/components/user/schemas';

/**
 * Build the URL for navigating to an active draft.
 */
function getDraftUrl(draft: ActiveDraftType): string {
  if (draft.type === 'team_draft') {
    return `/tournament/${draft.tournament_pk}/teams/draft`;
  }
  return `/tournament/${draft.tournament_pk}/bracket/draft/${draft.herodraft_pk}`;
}

/**
 * Get a display label for the draft type.
 */
function getDraftLabel(draft: ActiveDraftType): string {
  if (draft.type === 'team_draft') {
    return `Team Draft (Tournament ${draft.tournament_pk})`;
  }
  return `Hero Draft (Game ${draft.game_pk})`;
}

/**
 * Check if user is currently on a draft page.
 */
function isOnDraftPage(pathname: string): boolean {
  return pathname.includes('/draft');
}

/**
 * Banner displayed below navbar when user has active drafts.
 * Hidden on mobile (use FloatingDraftIndicator instead).
 * Hidden when user is on a draft page.
 */
export const ActiveDraftBanner: React.FC = () => {
  const [dismissed, setDismissed] = useState(false);
  const location = useLocation();
  const activeDrafts = useUserStore(
    (state) => state.currentUser?.active_drafts,
  );

  // Don't show if no active drafts, dismissed, or on draft page
  if (
    !activeDrafts ||
    activeDrafts.length === 0 ||
    dismissed ||
    isOnDraftPage(location.pathname)
  ) {
    return null;
  }

  const singleDraft = activeDrafts.length === 1;

  return (
    <div
      data-testid="active-draft-banner"
      className="hidden md:flex w-full bg-red-600 text-white px-4 py-2 items-center justify-center gap-3"
    >
      <ClipboardPen className="w-5 h-5 flex-shrink-0" />

      {singleDraft ? (
        // Single draft: direct link
        <a
          href={getDraftUrl(activeDrafts[0])}
          className="font-medium hover:underline"
        >
          You have an active {activeDrafts[0].type === 'team_draft' ? 'team' : 'hero'} draft - Click to join
        </a>
      ) : (
        // Multiple drafts: dropdown
        <div className="flex items-center gap-2">
          <span className="font-medium">
            You have {activeDrafts.length} active drafts
          </span>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="text-white hover:bg-red-700 h-7 px-2"
              >
                Select <ChevronDown className="ml-1 h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="center">
              {activeDrafts.map((draft, index) => (
                <DropdownMenuItem key={index} asChild>
                  <a href={getDraftUrl(draft)}>{getDraftLabel(draft)}</a>
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      )}

      <button
        onClick={() => setDismissed(true)}
        className="ml-auto p-1 hover:bg-red-700 rounded"
        aria-label="Dismiss banner"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
};
```

**Step 2: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft && git add frontend/app/components/draft/ActiveDraftBanner.tsx && git commit -m "feat(frontend): add ActiveDraftBanner component"
```

---

## Task 8: Frontend - Add ActiveDraftBanner to root layout

**Files:**
- Modify: Root layout file (find with grep)

**Step 1: Find the root layout**

Run: `grep -r "FloatingDraftIndicator" frontend/app --include="*.tsx" -l`

This will show where the floating indicator is placed - the banner should go in the same layout.

**Step 2: Import and add ActiveDraftBanner below navbar**

Add import:
```tsx
import { ActiveDraftBanner } from '~/components/draft/ActiveDraftBanner';
```

Add component after the navbar/header and before main content:
```tsx
<ActiveDraftBanner />
```

**Step 3: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft && git add <layout-file> && git commit -m "feat(frontend): add ActiveDraftBanner to layout"
```

---

## Task 9: Frontend - Rename Games tab to Bracket

**Files:**
- Modify: `frontend/app/pages/tournament/tabs/TournamentTabs.tsx`

**Step 1: Update tab label and value**

In `frontend/app/pages/tournament/tabs/TournamentTabs.tsx`, change:

Line 68-70:
```tsx
        <TabsTrigger value="bracket" data-testid="bracketTab">
          Bracket ({gameCount})
        </TabsTrigger>
```

Line 80-83:
```tsx
      <TabsContent value="bracket" data-testid="bracketTabContent">
        {' '}
        <GamesTab />
      </TabsContent>
```

**Step 2: Update tournamentStore default if needed**

Check `frontend/app/store/tournamentStore.ts` for default activeTab value. If it defaults to "games", update to "bracket" or keep "players".

**Step 3: Update Cypress tests**

Search for `gamesTab` or `value="games"` in Cypress tests and update:
- Change `data-testid="gamesTab"` to `data-testid="bracketTab"`
- Change `value="games"` to `value="bracket"`

Files likely affected:
- `frontend/tests/cypress/e2e/04-tournament/03-ui-elements.cy.ts`
- `frontend/tests/cypress/e2e/06-mobile/01-responsive.cy.ts`
- Other test files referencing the games tab

**Step 4: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft && git add frontend/app/pages/tournament/tabs/TournamentTabs.tsx frontend/app/store/tournamentStore.ts frontend/tests/cypress && git commit -m "feat(frontend): rename Games tab to Bracket"
```

---

## Task 10: Verify full integration

**Step 1: Run backend tests**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft && source .venv/bin/activate && inv test.run --cmd 'python manage.py test app.tests -v 2'
```

**Step 2: Run frontend type check**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft/frontend && npm run typecheck
```

**Step 3: Run Cypress tests**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft && source .venv/bin/activate && inv test.headless
```

**Step 4: Manual verification**

1. Start dev environment: `inv dev.debug`
2. Log in as a user who is captain
3. Navigate to a tournament with an active draft
4. Verify banner appears below navbar
5. Verify clicking navigates to draft page
6. Verify banner hides when on draft page

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Add active_drafts to current_user | `backend/app/views_main.py` |
| 2 | Remove deprecated endpoint | `backend/app/functions/tournament.py`, `backend/backend/urls.py` |
| 3 | Add ActiveDraftSchema | `frontend/app/components/user/schemas.ts` |
| 4 | Delete useActiveDraft hook | `frontend/app/hooks/useActiveDraft.ts` |
| 5 | Update DraftNotificationBadge | `frontend/app/components/draft/DraftNotificationBadge.tsx` |
| 6 | Update FloatingDraftIndicator | `frontend/app/components/draft/FloatingDraftIndicator.tsx` |
| 7 | Create ActiveDraftBanner | `frontend/app/components/draft/ActiveDraftBanner.tsx` |
| 8 | Add banner to layout | Root layout file |
| 9 | Rename Games to Bracket | `frontend/app/pages/tournament/tabs/TournamentTabs.tsx`, Cypress tests |
| 10 | Verify integration | Run tests |
