# Active Draft Context in Current User

**Status:** Completed

**Date:** 2026-01-21
**Status:** Approved

## Overview

Replace the separate polling endpoint `/active-draft-for-user/` with active draft information included in the `current_user` response. Support both team drafts and hero drafts, with a banner UI to notify users of active drafts.

## Current State

- `useActiveDraft.ts` polls `/active-draft-for-user/` every 5 seconds
- `get_active_draft_for_user()` only checks for pending team draft (DraftRound) turns
- No detection of active hero drafts

## Design

### Backend: `current_user` Response

Add `active_drafts` array to the existing user response:

```python
{
  # ... existing user fields ...
  "active_drafts": [
    {
      "type": "team_draft",
      "tournament_pk": 17,
      "draft_state": "in_progress"
    },
    {
      "type": "hero_draft",
      "tournament_pk": 17,
      "game_pk": 12,
      "herodraft_pk": 5,
      "draft_state": "drafting"
    }
  ]
}
```

**Query logic:**
- **Team draft:** `DraftRound` where user is captain, choice is null, tournament state is `in_progress`
- **Hero draft:** `HeroDraft` where user is captain of a `DraftTeam`, state in `[waiting_for_captains, rolling, choosing, drafting]`

### Frontend: URL Construction

Frontend constructs display URLs from the data:
- **Team draft:** `/tournament/${tournament_pk}/teams/draft`
- **Hero draft:** `/tournament/${tournament_pk}/bracket/draft/${herodraft_pk}`

### Frontend: ActiveDraftBanner Component

- Renders below navbar on desktop
- Hidden when user is on a draft page
- Single banner with count badge when multiple drafts
- Dropdown to select which draft to navigate to
- Mobile uses existing floating indicator

### Additional Change: Rename Tab

Rename "Games" tab to "Bracket" in tournament page navigation.

## Files to Change

### Backend
- `backend/app/views/__init__.py` - update `current_user` view to include `active_drafts`
- `backend/app/functions/tournament.py` - remove `get_active_draft_for_user` function
- `backend/backend/urls.py` - remove `/active-draft-for-user/` route

### Frontend
- `frontend/app/hooks/useActiveDraft.ts` - delete file
- `frontend/app/store/userStore.ts` - add `active_drafts` type to user
- `frontend/app/components/draft/DraftNotificationBadge.tsx` - update to use store
- `frontend/app/components/draft/FloatingDraftIndicator.tsx` - update to use store
- New: `frontend/app/components/draft/ActiveDraftBanner.tsx` - banner component
- Tournament page tabs - rename "Games" to "Bracket"

## What We're Removing

- Separate `/active-draft-for-user/` endpoint
- 5-second polling interval
- `ActiveDraftManager` singleton class in `useActiveDraft.ts`

## What We're Adding

- `active_drafts` array in `current_user` response
- `ActiveDraftBanner` component below navbar
- Hero draft detection (not just team draft)

## Migration

No database migration required - purely response shape and UI changes.
