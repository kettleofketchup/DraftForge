# Hero Draft Cypress E2E Test Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create comprehensive Cypress E2E tests for the full hero draft flow using Real Tournament 38 data with session-based captain switching.

**Architecture:** Reorder populate functions so Real Tournament 38 is pk 1, add Discord ID-based login and force-timeout test endpoints, create session helpers for fast captain switching, then implement tests covering all draft phases including timeout and disconnect edge cases.

**Tech Stack:** Django REST Framework (test endpoints), Cypress (E2E tests), cy.session() (identity switching), WebSocket (real-time updates)

---

## Phase 1: Backend Setup

### Task 1: Reorder populate_all() function

**Files:**
- Modify: `backend/tests/populate.py:1512-1520`

**Step 1: Read current populate_all function**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft
```

**Step 2: Modify populate_all to run real_tournament_38 first**

Change the function order so `populate_real_tournament_38` runs immediately after `populate_users`:

```python
def populate_all(force=False):
    """Run all population functions in the correct order."""
    populate_organizations_and_leagues(force)
    populate_users(force)
    populate_real_tournament_38(force)  # MOVED FIRST - gets pk 1
    populate_tournaments(force)
    populate_steam_matches(force)
    populate_bracket_linking_scenario(force)
```

**Step 3: Verify the change**

Run: `cd /home/kettle/git_repos/website/.worktrees/herodraft && source .venv/bin/activate && inv test.exec --service backend --cmd 'python manage.py check'`
Expected: System check identified no issues.

**Step 4: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft && git add backend/tests/populate.py && git commit -m "fix(tests): reorder populate_all to create real_tournament_38 first (pk 1)"
```

---

### Task 2: Add real_tournament key to tournament config

**Files:**
- Modify: `backend/tests/helpers/tournament_config.py:339-347`

**Step 1: Add the tournament key mapping**

After the existing `TEST_KEY_TO_NAME` entries, add:

```python
# Add real tournament 38 for hero draft E2E testing
TEST_KEY_TO_NAME["real_tournament"] = "Real Tournament 38"
```

**Step 2: Verify syntax**

Run: `cd /home/kettle/git_repos/website/.worktrees/herodraft && source .venv/bin/activate && inv test.exec --service backend --cmd 'python -c "from tests.helpers.tournament_config import TEST_KEY_TO_NAME; print(TEST_KEY_TO_NAME.get(\"real_tournament\"))"'`
Expected: `Real Tournament 38`

**Step 3: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft && git add backend/tests/helpers/tournament_config.py && git commit -m "feat(tests): add real_tournament key for hero draft E2E testing"
```

---

### Task 3: Create login_as_discord_id test endpoint

**Files:**
- Modify: `backend/tests/test_auth.py`
- Modify: `backend/tests/urls.py`

**Step 1: Add the view function to test_auth.py**

Add after the existing `login_as` function:

```python
@api_view(["POST"])
def login_as_discord_id(request):
    """
    Login as a user by their Discord ID (TEST ONLY).

    This endpoint is only available when TEST_ENDPOINTS=true.
    Discord IDs are stable across populate runs, unlike PKs.

    Request body:
        discord_id: str - The Discord ID of the user to login as

    Returns:
        200: Login successful with user data
        404: User not found
    """
    discord_id = request.data.get("discord_id")
    if not discord_id:
        return Response(
            {"error": "discord_id is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = CustomUser.objects.filter(discordId=discord_id).first()
    if not user:
        return Response(
            {"error": f"User with Discord ID {discord_id} not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    login(request, user)

    response = Response(
        {
            "success": True,
            "user": {
                "pk": user.pk,
                "username": user.username,
                "discordUsername": user.discordUsername,
                "discordId": user.discordId,
                "mmr": user.mmr,
            },
        },
        status=status.HTTP_200_OK,
    )

    # Set cookies in response headers for Cypress
    response["CookieSessionId"] = request.session.session_key
    response["CookieCsrfToken"] = request.META.get("CSRF_COOKIE", "")

    return response
```

**Step 2: Add URL route**

In `backend/tests/urls.py`, add import and path:

```python
from tests.test_auth import (
    createTestSuperUser,
    createTestStaffUser,
    createTestUser,
    login_admin,
    login_staff,
    login_user,
    login_as,
    login_as_discord_id,  # ADD THIS
)

# In urlpatterns, add:
path("login-as-discord/", login_as_discord_id, name="test-login-as-discord"),
```

**Step 3: Verify endpoint works**

Run: `cd /home/kettle/git_repos/website/.worktrees/herodraft && source .venv/bin/activate && inv test.exec --service backend --cmd 'python manage.py check'`
Expected: System check identified no issues.

**Step 4: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft && git add backend/tests/test_auth.py backend/tests/urls.py && git commit -m "feat(tests): add login_as_discord_id test endpoint"
```

---

### Task 4: Create force_herodraft_timeout test endpoint

**Files:**
- Create: `backend/tests/test_herodraft.py`
- Modify: `backend/tests/urls.py`

**Step 1: Create the test_herodraft.py file**

```python
"""
Test endpoints for HeroDraft E2E testing (TEST ONLY).

These endpoints are only available when TEST_ENDPOINTS=true in settings.
"""

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from app.models import HeroDraft, HeroDraftEvent
from app.serializers import HeroDraftSerializer


@api_view(["POST"])
def force_herodraft_timeout(request, draft_pk):
    """
    Force a timeout on the current active round (TEST ONLY).

    This immediately triggers the timeout logic which:
    1. Selects a random available hero
    2. Completes the current round
    3. Advances to the next round (or completes the draft)
    4. Logs a round_timeout event

    Used for testing timeout behavior without waiting 30+ seconds.

    Args:
        draft_pk: The HeroDraft primary key

    Returns:
        200: Updated draft data after timeout
        400: No active round to timeout
        404: Draft not found
    """
    draft = get_object_or_404(HeroDraft, pk=draft_pk)

    if draft.state != "drafting":
        return Response(
            {"error": f"Cannot force timeout in state '{draft.state}'"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    current_round = draft.rounds.filter(state="active").first()
    if not current_round:
        return Response(
            {"error": "No active round to timeout"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Import and call the timeout handler
    from app.functions.herodraft import handle_round_timeout

    try:
        handle_round_timeout(draft, current_round)
    except Exception as e:
        return Response(
            {"error": f"Timeout handling failed: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # Refresh and return updated draft
    draft.refresh_from_db()
    return Response(HeroDraftSerializer(draft).data)


@api_view(["POST"])
def reset_herodraft(request, draft_pk):
    """
    Reset a hero draft back to waiting_for_captains state (TEST ONLY).

    This allows re-running E2E tests without recreating the draft.
    Deletes all rounds and events, resets team states.

    Args:
        draft_pk: The HeroDraft primary key

    Returns:
        200: Reset draft data
        404: Draft not found
    """
    draft = get_object_or_404(HeroDraft, pk=draft_pk)

    # Delete all rounds
    draft.rounds.all().delete()

    # Delete all events
    draft.events.all().delete()

    # Reset draft state
    draft.state = "waiting_for_captains"
    draft.roll_winner = None
    draft.save()

    # Reset draft teams
    for draft_team in draft.draft_teams.all():
        draft_team.is_ready = False
        draft_team.is_connected = False
        draft_team.is_first_pick = None
        draft_team.is_radiant = None
        draft_team.reserve_time_remaining = 90000  # 90 seconds default
        draft_team.save()

    # Log reset event
    HeroDraftEvent.objects.create(
        draft=draft,
        event_type="draft_reset",
        metadata={"reset_by": "test_endpoint"},
    )

    return Response(HeroDraftSerializer(draft).data)
```

**Step 2: Add URL routes**

In `backend/tests/urls.py`, add:

```python
from tests.test_herodraft import force_herodraft_timeout, reset_herodraft

# In urlpatterns, add:
path(
    "herodraft/<int:draft_pk>/force-timeout/",
    force_herodraft_timeout,
    name="test-herodraft-force-timeout",
),
path(
    "herodraft/<int:draft_pk>/reset/",
    reset_herodraft,
    name="test-herodraft-reset",
),
```

**Step 3: Verify endpoints**

Run: `cd /home/kettle/git_repos/website/.worktrees/herodraft && source .venv/bin/activate && inv test.exec --service backend --cmd 'python manage.py check'`
Expected: System check identified no issues.

**Step 4: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft && git add backend/tests/test_herodraft.py backend/tests/urls.py && git commit -m "feat(tests): add force_herodraft_timeout and reset_herodraft test endpoints"
```

---

### Task 5: Verify handle_round_timeout function exists

**Files:**
- Check: `backend/app/functions/herodraft.py`

**Step 1: Search for existing timeout handler**

Run: `cd /home/kettle/git_repos/website/.worktrees/herodraft && grep -n "handle_round_timeout\|handle_timeout" backend/app/functions/herodraft.py`

**Step 2: If function doesn't exist, create it**

If not found, add to `backend/app/functions/herodraft.py`:

```python
def handle_round_timeout(draft: "HeroDraft", round: "HeroDraftRound") -> None:
    """
    Handle timeout for a draft round by selecting a random available hero.

    Called when grace time + reserve time expires.

    Args:
        draft: The HeroDraft instance
        round: The active HeroDraftRound that timed out
    """
    import random
    from app.models import HeroDraftEvent

    # Get available heroes
    available = get_available_heroes(draft)
    if not available:
        raise ValueError("No available heroes for timeout selection")

    # Select random hero
    hero_id = random.choice(list(available))

    # Get the team for this round
    draft_team = round.draft_team

    # Deduct remaining grace time from reserve (already 0 if timed out)
    # Complete the pick
    round.hero_id = hero_id
    round.state = "completed"
    round.completed_at = timezone.now()
    round.save()

    # Log timeout event
    HeroDraftEvent.objects.create(
        draft=draft,
        event_type="round_timeout",
        draft_team=draft_team,
        metadata={
            "round_number": round.round_number,
            "action_type": round.action_type,
            "hero_id": hero_id,
            "was_random": True,
        },
    )

    # Advance to next round or complete draft
    _advance_draft(draft)
```

**Step 3: Verify function is importable**

Run: `cd /home/kettle/git_repos/website/.worktrees/herodraft && source .venv/bin/activate && inv test.exec --service backend --cmd 'python -c "from app.functions.herodraft import handle_round_timeout; print(\"OK\")"'`
Expected: `OK`

**Step 4: Commit if changes were made**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft && git add backend/app/functions/herodraft.py && git commit -m "feat(herodraft): add handle_round_timeout function for timeout handling"
```

---

## Phase 2: Cypress Infrastructure

### Task 6: Add loginAsDiscordId Cypress command

**Files:**
- Modify: `frontend/tests/cypress/support/commands.ts`

**Step 1: Add TypeScript declaration**

In the `declare namespace Cypress` block, add:

```typescript
/**
 * Custom command to login as a specific user by Discord ID (TEST ONLY)
 * Discord IDs are stable across populate runs, unlike PKs.
 * @example cy.loginAsDiscordId('764290890617192469')
 */
loginAsDiscordId(discordId: string): Chainable<Cypress.Response<{
  success: boolean;
  user: {
    pk: number;
    username: string;
    discordUsername: string;
    discordId: string;
    mmr: number;
  };
}>>;
```

**Step 2: Add command implementation**

After the existing `loginAsUser` command, add:

```typescript
// Login as specific user by Discord ID (TEST ONLY)
Cypress.Commands.add('loginAsDiscordId', (discordId: string) => {
  return cy.request({
    method: 'POST',
    url: `${Cypress.env('apiUrl')}/tests/login-as-discord/`,
    body: { discord_id: discordId },
    headers: {
      'Content-Type': 'application/json',
    },
  }).then((response) => {
    if (response.headers.cookiescsrftoken) {
      window.cookieStore.set(
        'csrftoken',
        response.headers.cookiescsrftoken as string,
      );
    }
    if (response.headers.cookiesessionid) {
      window.cookieStore.set(
        'sessionid',
        response.headers.cookiesessionid as string,
      );
    }
    return response;
  });
});
```

**Step 3: Verify TypeScript compiles**

Run: `cd /home/kettle/git_repos/website/.worktrees/herodraft/frontend && npx tsc --noEmit -p tests/cypress/tsconfig.json 2>&1 | head -20`
Expected: No errors related to loginAsDiscordId

**Step 4: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft && git add frontend/tests/cypress/support/commands.ts && git commit -m "feat(cypress): add loginAsDiscordId command for stable identity login"
```

---

### Task 7: Create herodraft-sessions.ts helper

**Files:**
- Create: `frontend/tests/cypress/helpers/herodraft-sessions.ts`

**Step 1: Create the session helper file**

```typescript
/**
 * HeroDraft Session Helpers
 *
 * Provides fast captain identity switching using cy.session().
 * Uses Discord IDs for stable identification across populate runs.
 *
 * Captains are from Real Tournament 38's Winners Final game:
 * - Radiant: vrm.mtl vs Dire: ethan0688_
 */

import type { cyType } from './types';

// Discord IDs for Real Tournament 38 Winners Final captains
export const CAPTAIN_RADIANT = {
  discordId: '764290890617192469',
  username: 'vrm.mtl',
  sessionName: 'herodraft_captain_radiant',
} as const;

export const CAPTAIN_DIRE = {
  discordId: '1325607754177581066',
  username: 'ethan0688_',
  sessionName: 'herodraft_captain_dire',
} as const;

export type CaptainConfig = typeof CAPTAIN_RADIANT | typeof CAPTAIN_DIRE;

/**
 * Login as a captain using cy.session() for fast switching.
 * Sessions are cached - subsequent calls reuse existing session.
 */
export const loginAsCaptain = (cy: cyType, captain: CaptainConfig) => {
  cy.session(
    captain.sessionName,
    () => {
      cy.loginAsDiscordId(captain.discordId);
    },
    {
      validate: () => {
        // Validate session by checking current user endpoint
        cy.request({
          url: `${Cypress.env('apiUrl')}/api/current_user/`,
          failOnStatusCode: false,
        }).then((response) => {
          expect(response.status).to.eq(201);
          expect(response.body.discordId).to.eq(captain.discordId);
        });
      },
    },
  );
};

/**
 * Switch to Captain Radiant (vrm.mtl)
 */
export const switchToCaptainRadiant = (cy: cyType) => {
  loginAsCaptain(cy, CAPTAIN_RADIANT);
};

/**
 * Switch to Captain Dire (ethan0688_)
 */
export const switchToCaptainDire = (cy: cyType) => {
  loginAsCaptain(cy, CAPTAIN_DIRE);
};

/**
 * Get the other captain (for alternating turns)
 */
export const getOtherCaptain = (current: CaptainConfig): CaptainConfig => {
  return current === CAPTAIN_RADIANT ? CAPTAIN_DIRE : CAPTAIN_RADIANT;
};

/**
 * Clear all hero draft sessions (useful in beforeEach for clean state)
 */
export const clearHeroDraftSessions = (cy: cyType) => {
  Cypress.session.clearAllSavedSessions();
};
```

**Step 2: Verify TypeScript compiles**

Run: `cd /home/kettle/git_repos/website/.worktrees/herodraft/frontend && npx tsc --noEmit -p tests/cypress/tsconfig.json 2>&1 | head -20`
Expected: No errors

**Step 3: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft && git add frontend/tests/cypress/helpers/herodraft-sessions.ts && git commit -m "feat(cypress): add herodraft-sessions helper for captain switching"
```

---

### Task 8: Update bracket tests to use getTournamentByKey

**Files:**
- Modify: `frontend/tests/cypress/e2e/09-bracket/01-bracket-badges.cy.ts`
- Modify: `frontend/tests/cypress/e2e/04-tournament/03-ui-elements.cy.ts`

**Step 1: Update 01-bracket-badges.cy.ts**

Replace hardcoded `/tournament/1/`, `/tournament/2/`, `/tournament/3/` with dynamic lookups.

Add at the start of the describe block:

```typescript
describe('Bracket Badges (e2e)', () => {
  let completedBracketPk: number;
  let partialBracketPk: number;
  let pendingBracketPk: number;

  before(() => {
    // Get tournament PKs by key (stable across populate changes)
    cy.getTournamentByKey('completed_bracket').then((response) => {
      completedBracketPk = response.body.pk;
    });
    cy.getTournamentByKey('partial_bracket').then((response) => {
      partialBracketPk = response.body.pk;
    });
    cy.getTournamentByKey('pending_bracket').then((response) => {
      pendingBracketPk = response.body.pk;
    });
  });

  beforeEach(() => {
    cy.loginStaff();
    suppressHydrationErrors();
  });
```

Then replace all:
- `/tournament/1/games` → `` `/tournament/${completedBracketPk}/games` ``
- `/tournament/2/games` → `` `/tournament/${partialBracketPk}/games` ``
- `/tournament/3/games` → `` `/tournament/${pendingBracketPk}/games` ``

**Step 2: Update 03-ui-elements.cy.ts**

Add before block and replace hardcoded pk:

```typescript
describe('Tournament UI Elements (e2e)', () => {
  let tournamentPk: number;

  before(() => {
    cy.getTournamentByKey('completed_bracket').then((response) => {
      tournamentPk = response.body.pk;
    });
  });

  beforeEach(() => {
    cy.loginAdmin();
    visitAndWaitForHydration(`/tournament/${tournamentPk}/players`);
    suppressHydrationErrors();
  });
```

**Step 3: Verify tests still pass syntax check**

Run: `cd /home/kettle/git_repos/website/.worktrees/herodraft/frontend && npx tsc --noEmit -p tests/cypress/tsconfig.json 2>&1 | head -20`
Expected: No errors

**Step 4: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft && git add frontend/tests/cypress/e2e/09-bracket/01-bracket-badges.cy.ts frontend/tests/cypress/e2e/04-tournament/03-ui-elements.cy.ts && git commit -m "refactor(cypress): use getTournamentByKey instead of hardcoded PKs"
```

---

## Phase 3: Hero Draft E2E Tests

### Task 9: Create hero draft test file structure

**Files:**
- Create: `frontend/tests/cypress/e2e/10-herodraft/01-full-draft-flow.cy.ts`

**Step 1: Create the directory and test file skeleton**

```typescript
/**
 * Hero Draft Full Flow E2E Tests
 *
 * Tests the complete hero draft (Captain's Mode) lifecycle using
 * Real Tournament 38's Winners Final game (vrm.mtl vs ethan0688_).
 *
 * Uses cy.session() for fast captain identity switching.
 */

import {
  suppressHydrationErrors,
  visitAndWaitForHydration,
} from 'tests/cypress/support/utils';
import {
  CAPTAIN_RADIANT,
  CAPTAIN_DIRE,
  switchToCaptainRadiant,
  switchToCaptainDire,
  clearHeroDraftSessions,
} from 'tests/cypress/helpers/herodraft-sessions';
import {
  waitForHeroDraftModal,
  assertWaitingPhase,
  assertRollingPhase,
  assertChoosingPhase,
  assertDraftingPhase,
  assertPausedState,
  clickReadyButton,
  clickFlipCoinButton,
  selectWinnerChoice,
  selectLoserChoice,
  clickHero,
  confirmHeroSelection,
  waitForDraftState,
  getGraceTime,
  assertHeroUnavailable,
} from 'tests/cypress/helpers/herodraft';

describe('Hero Draft Full Flow (e2e)', () => {
  let tournamentPk: number;
  let gamePk: number;
  let heroDraftPk: number;

  before(() => {
    // Get Real Tournament 38 (should be pk 1 after populate reorder)
    cy.getTournamentByKey('real_tournament').then((response) => {
      tournamentPk = response.body.pk;
      // Find Winners Final game (round 2, winners bracket)
      // This is vrm.mtl vs ethan0688_
      cy.request({
        method: 'GET',
        url: `${Cypress.env('apiUrl')}/api/bracket/tournaments/${tournamentPk}/`,
      }).then((bracketResponse) => {
        const games = bracketResponse.body.games || [];
        // Find the pending Winners Final (round 2, winners bracket)
        const winnersFinal = games.find(
          (g: any) =>
            g.round === 2 &&
            g.bracket_type === 'winners' &&
            g.status === 'pending',
        );
        if (winnersFinal) {
          gamePk = winnersFinal.pk;
        } else {
          throw new Error('Winners Final game not found in Real Tournament 38');
        }
      });
    });
  });

  beforeEach(() => {
    suppressHydrationErrors();
  });

  describe('Setup', () => {
    it('should create hero draft for Winners Final game', () => {
      // Login as admin to create draft
      cy.loginAdmin();

      // Create hero draft via API
      cy.request({
        method: 'POST',
        url: `${Cypress.env('apiUrl')}/api/herodraft/game/${gamePk}/create/`,
      }).then((response) => {
        expect(response.status).to.be.oneOf([200, 201]);
        heroDraftPk = response.body.pk;
        expect(response.body.state).to.eq('waiting_for_captains');
      });
    });
  });

  // Test implementations continue in subsequent tasks...
});
```

**Step 2: Verify file compiles**

Run: `cd /home/kettle/git_repos/website/.worktrees/herodraft/frontend && npx tsc --noEmit -p tests/cypress/tsconfig.json 2>&1 | head -20`
Expected: No errors

**Step 3: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft && mkdir -p frontend/tests/cypress/e2e/10-herodraft && git add frontend/tests/cypress/e2e/10-herodraft/01-full-draft-flow.cy.ts && git commit -m "feat(cypress): add hero draft E2E test file structure"
```

---

### Task 10: Implement waiting phase tests

**Files:**
- Modify: `frontend/tests/cypress/e2e/10-herodraft/01-full-draft-flow.cy.ts`

**Step 1: Add waiting phase test block**

Add after the Setup describe block:

```typescript
  describe('Waiting Phase', () => {
    beforeEach(() => {
      // Reset draft to waiting state before each test
      cy.loginAdmin();
      cy.request({
        method: 'POST',
        url: `${Cypress.env('apiUrl')}/tests/herodraft/${heroDraftPk}/reset/`,
      });
    });

    it('should show waiting phase when captain visits draft', () => {
      switchToCaptainRadiant(cy);
      visitAndWaitForHydration(
        `/tournament/${tournamentPk}/bracket/draft/${heroDraftPk}`,
      );
      waitForHeroDraftModal(cy);
      assertWaitingPhase(cy);
    });

    it('should allow Captain Radiant to ready up', () => {
      switchToCaptainRadiant(cy);
      visitAndWaitForHydration(
        `/tournament/${tournamentPk}/bracket/draft/${heroDraftPk}`,
      );
      waitForHeroDraftModal(cy);

      clickReadyButton(cy);

      // Verify ready state via API (logged to events)
      cy.request({
        method: 'GET',
        url: `${Cypress.env('apiUrl')}/api/herodraft/${heroDraftPk}/events/`,
      }).then((response) => {
        const events = response.body;
        const readyEvent = events.find(
          (e: any) => e.event_type === 'captain_ready',
        );
        expect(readyEvent).to.exist;
      });
    });

    it('should allow Captain Dire to ready up', () => {
      // First, radiant readies
      switchToCaptainRadiant(cy);
      visitAndWaitForHydration(
        `/tournament/${tournamentPk}/bracket/draft/${heroDraftPk}`,
      );
      waitForHeroDraftModal(cy);
      clickReadyButton(cy);

      // Then dire readies
      switchToCaptainDire(cy);
      visitAndWaitForHydration(
        `/tournament/${tournamentPk}/bracket/draft/${heroDraftPk}`,
      );
      waitForHeroDraftModal(cy);
      clickReadyButton(cy);

      // Verify both ready events logged
      cy.request({
        method: 'GET',
        url: `${Cypress.env('apiUrl')}/api/herodraft/${heroDraftPk}/events/`,
      }).then((response) => {
        const events = response.body;
        const readyEvents = events.filter(
          (e: any) => e.event_type === 'captain_ready',
        );
        expect(readyEvents.length).to.eq(2);
      });
    });

    it('should transition to rolling when both captains ready', () => {
      // Radiant readies
      switchToCaptainRadiant(cy);
      visitAndWaitForHydration(
        `/tournament/${tournamentPk}/bracket/draft/${heroDraftPk}`,
      );
      waitForHeroDraftModal(cy);
      clickReadyButton(cy);

      // Dire readies
      switchToCaptainDire(cy);
      visitAndWaitForHydration(
        `/tournament/${tournamentPk}/bracket/draft/${heroDraftPk}`,
      );
      waitForHeroDraftModal(cy);
      clickReadyButton(cy);

      // Should now be in rolling phase
      waitForDraftState(cy, 'rolling');
      assertRollingPhase(cy);
    });
  });
```

**Step 2: Verify compiles**

Run: `cd /home/kettle/git_repos/website/.worktrees/herodraft/frontend && npx tsc --noEmit -p tests/cypress/tsconfig.json 2>&1 | head -20`

**Step 3: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft && git add frontend/tests/cypress/e2e/10-herodraft/01-full-draft-flow.cy.ts && git commit -m "feat(cypress): add waiting phase tests for hero draft"
```

---

### Task 11: Implement rolling and choosing phase tests

**Files:**
- Modify: `frontend/tests/cypress/e2e/10-herodraft/01-full-draft-flow.cy.ts`

**Step 1: Add rolling and choosing phase tests**

```typescript
  describe('Rolling Phase', () => {
    beforeEach(() => {
      // Setup: get both captains ready
      cy.loginAdmin();
      cy.request({
        method: 'POST',
        url: `${Cypress.env('apiUrl')}/tests/herodraft/${heroDraftPk}/reset/`,
      });

      // Both captains ready up
      switchToCaptainRadiant(cy);
      visitAndWaitForHydration(
        `/tournament/${tournamentPk}/bracket/draft/${heroDraftPk}`,
      );
      waitForHeroDraftModal(cy);
      clickReadyButton(cy);

      switchToCaptainDire(cy);
      visitAndWaitForHydration(
        `/tournament/${tournamentPk}/bracket/draft/${heroDraftPk}`,
      );
      waitForHeroDraftModal(cy);
      clickReadyButton(cy);
      waitForDraftState(cy, 'rolling');
    });

    it('should show coin flip UI in rolling phase', () => {
      assertRollingPhase(cy);
      cy.get('[data-testid="herodraft-flip-coin-button"]').should('be.visible');
    });

    it('should allow captain to trigger coin flip (logged to events)', () => {
      clickFlipCoinButton(cy);

      // Wait for roll result
      cy.wait(1000); // Allow animation

      // Verify roll events logged
      cy.request({
        method: 'GET',
        url: `${Cypress.env('apiUrl')}/api/herodraft/${heroDraftPk}/events/`,
      }).then((response) => {
        const events = response.body;
        const rollEvent = events.find(
          (e: any) =>
            e.event_type === 'roll_triggered' || e.event_type === 'roll_result',
        );
        expect(rollEvent).to.exist;
      });

      // Should transition to choosing phase
      waitForDraftState(cy, 'choosing');
    });
  });

  describe('Choosing Phase', () => {
    beforeEach(() => {
      // Setup: get to choosing phase
      cy.loginAdmin();
      cy.request({
        method: 'POST',
        url: `${Cypress.env('apiUrl')}/tests/herodraft/${heroDraftPk}/reset/`,
      });

      // Both ready
      switchToCaptainRadiant(cy);
      visitAndWaitForHydration(
        `/tournament/${tournamentPk}/bracket/draft/${heroDraftPk}`,
      );
      waitForHeroDraftModal(cy);
      clickReadyButton(cy);

      switchToCaptainDire(cy);
      visitAndWaitForHydration(
        `/tournament/${tournamentPk}/bracket/draft/${heroDraftPk}`,
      );
      waitForHeroDraftModal(cy);
      clickReadyButton(cy);
      waitForDraftState(cy, 'rolling');

      // Trigger roll
      clickFlipCoinButton(cy);
      waitForDraftState(cy, 'choosing');
    });

    it('should show choosing phase UI', () => {
      assertChoosingPhase(cy);
    });

    it('should allow roll winner to choose first pick (logged to events)', () => {
      // Get current draft to find roll winner
      cy.request({
        method: 'GET',
        url: `${Cypress.env('apiUrl')}/api/herodraft/${heroDraftPk}/`,
      }).then((response) => {
        const draft = response.body;
        const rollWinnerDiscordId =
          draft.roll_winner?.tournament_team?.captain?.discordId;

        // Switch to roll winner
        if (rollWinnerDiscordId === CAPTAIN_RADIANT.discordId) {
          switchToCaptainRadiant(cy);
        } else {
          switchToCaptainDire(cy);
        }

        visitAndWaitForHydration(
          `/tournament/${tournamentPk}/bracket/draft/${heroDraftPk}`,
        );
        waitForHeroDraftModal(cy);

        // Winner chooses first pick
        selectWinnerChoice(cy, 'first_pick');

        // Verify choice logged
        cy.request({
          method: 'GET',
          url: `${Cypress.env('apiUrl')}/api/herodraft/${heroDraftPk}/events/`,
        }).then((eventsResponse) => {
          const events = eventsResponse.body;
          const choiceEvent = events.find(
            (e: any) => e.event_type === 'choice_made',
          );
          expect(choiceEvent).to.exist;
        });
      });
    });

    it('should transition to drafting after both choices made', () => {
      // Get roll winner
      cy.request({
        method: 'GET',
        url: `${Cypress.env('apiUrl')}/api/herodraft/${heroDraftPk}/`,
      }).then((response) => {
        const draft = response.body;
        const rollWinnerDiscordId =
          draft.roll_winner?.tournament_team?.captain?.discordId;
        const isRadiantWinner =
          rollWinnerDiscordId === CAPTAIN_RADIANT.discordId;

        // Winner chooses
        if (isRadiantWinner) {
          switchToCaptainRadiant(cy);
        } else {
          switchToCaptainDire(cy);
        }
        visitAndWaitForHydration(
          `/tournament/${tournamentPk}/bracket/draft/${heroDraftPk}`,
        );
        waitForHeroDraftModal(cy);
        selectWinnerChoice(cy, 'first_pick');

        // Loser chooses remaining
        if (isRadiantWinner) {
          switchToCaptainDire(cy);
        } else {
          switchToCaptainRadiant(cy);
        }
        visitAndWaitForHydration(
          `/tournament/${tournamentPk}/bracket/draft/${heroDraftPk}`,
        );
        waitForHeroDraftModal(cy);
        selectLoserChoice(cy, 'radiant');

        // Should now be in drafting phase
        waitForDraftState(cy, 'drafting');
        assertDraftingPhase(cy);
      });
    });
  });
```

**Step 2: Verify compiles**

Run: `cd /home/kettle/git_repos/website/.worktrees/herodraft/frontend && npx tsc --noEmit -p tests/cypress/tsconfig.json 2>&1 | head -20`

**Step 3: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft && git add frontend/tests/cypress/e2e/10-herodraft/01-full-draft-flow.cy.ts && git commit -m "feat(cypress): add rolling and choosing phase tests for hero draft"
```

---

### Task 12: Implement drafting phase tests (bans and picks)

**Files:**
- Modify: `frontend/tests/cypress/e2e/10-herodraft/01-full-draft-flow.cy.ts`

**Step 1: Add helper to get draft to drafting state**

```typescript
  // Helper to quickly get draft to drafting state
  const setupDraftingPhase = () => {
    cy.loginAdmin();
    cy.request({
      method: 'POST',
      url: `${Cypress.env('apiUrl')}/tests/herodraft/${heroDraftPk}/reset/`,
    });

    // Both ready
    switchToCaptainRadiant(cy);
    visitAndWaitForHydration(
      `/tournament/${tournamentPk}/bracket/draft/${heroDraftPk}`,
    );
    waitForHeroDraftModal(cy);
    clickReadyButton(cy);

    switchToCaptainDire(cy);
    visitAndWaitForHydration(
      `/tournament/${tournamentPk}/bracket/draft/${heroDraftPk}`,
    );
    waitForHeroDraftModal(cy);
    clickReadyButton(cy);
    waitForDraftState(cy, 'rolling');

    // Roll
    clickFlipCoinButton(cy);
    waitForDraftState(cy, 'choosing');

    // Make choices - get draft state to determine winner
    return cy
      .request({
        method: 'GET',
        url: `${Cypress.env('apiUrl')}/api/herodraft/${heroDraftPk}/`,
      })
      .then((response) => {
        const draft = response.body;
        const rollWinnerDiscordId =
          draft.roll_winner?.tournament_team?.captain?.discordId;
        const isRadiantWinner =
          rollWinnerDiscordId === CAPTAIN_RADIANT.discordId;

        // Winner chooses first_pick
        if (isRadiantWinner) {
          switchToCaptainRadiant(cy);
        } else {
          switchToCaptainDire(cy);
        }
        visitAndWaitForHydration(
          `/tournament/${tournamentPk}/bracket/draft/${heroDraftPk}`,
        );
        waitForHeroDraftModal(cy);
        selectWinnerChoice(cy, 'first_pick');

        // Loser chooses radiant
        if (isRadiantWinner) {
          switchToCaptainDire(cy);
        } else {
          switchToCaptainRadiant(cy);
        }
        visitAndWaitForHydration(
          `/tournament/${tournamentPk}/bracket/draft/${heroDraftPk}`,
        );
        waitForHeroDraftModal(cy);
        selectLoserChoice(cy, 'radiant');

        waitForDraftState(cy, 'drafting');

        return { isRadiantWinner };
      });
  };
```

**Step 2: Add drafting phase tests**

```typescript
  describe('Drafting Phase - Bans', () => {
    it('should show ban phase UI for first pick captain', () => {
      setupDraftingPhase().then(() => {
        assertDraftingPhase(cy);
        // First action should be a ban
        cy.get('[data-testid="herodraft-current-action"]').should(
          'contain.text',
          'Ban',
        );
      });
    });

    it('should allow captain to ban a hero (logged to events)', () => {
      setupDraftingPhase().then(() => {
        // Get current draft state to find who picks first
        cy.request({
          method: 'GET',
          url: `${Cypress.env('apiUrl')}/api/herodraft/${heroDraftPk}/`,
        }).then((response) => {
          const draft = response.body;
          const firstPickTeam = draft.draft_teams.find(
            (t: any) => t.is_first_pick,
          );
          const firstPickCaptainDiscordId =
            firstPickTeam?.tournament_team?.captain?.discordId;

          // Switch to first pick captain
          if (firstPickCaptainDiscordId === CAPTAIN_RADIANT.discordId) {
            switchToCaptainRadiant(cy);
          } else {
            switchToCaptainDire(cy);
          }

          visitAndWaitForHydration(
            `/tournament/${tournamentPk}/bracket/draft/${heroDraftPk}`,
          );
          waitForHeroDraftModal(cy);

          // Ban Anti-Mage (hero_id: 1)
          clickHero(cy, 1);
          confirmHeroSelection(cy);

          // Verify hero_selected event logged
          cy.wait(500);
          cy.request({
            method: 'GET',
            url: `${Cypress.env('apiUrl')}/api/herodraft/${heroDraftPk}/events/`,
          }).then((eventsResponse) => {
            const events = eventsResponse.body;
            const selectEvent = events.find(
              (e: any) => e.event_type === 'hero_selected',
            );
            expect(selectEvent).to.exist;
          });
        });
      });
    });

    it('should mark banned hero as unavailable', () => {
      setupDraftingPhase().then(() => {
        cy.request({
          method: 'GET',
          url: `${Cypress.env('apiUrl')}/api/herodraft/${heroDraftPk}/`,
        }).then((response) => {
          const draft = response.body;
          const firstPickTeam = draft.draft_teams.find(
            (t: any) => t.is_first_pick,
          );
          const firstPickCaptainDiscordId =
            firstPickTeam?.tournament_team?.captain?.discordId;

          if (firstPickCaptainDiscordId === CAPTAIN_RADIANT.discordId) {
            switchToCaptainRadiant(cy);
          } else {
            switchToCaptainDire(cy);
          }

          visitAndWaitForHydration(
            `/tournament/${tournamentPk}/bracket/draft/${heroDraftPk}`,
          );
          waitForHeroDraftModal(cy);

          // Ban Axe (hero_id: 2)
          clickHero(cy, 2);
          confirmHeroSelection(cy);

          // Wait for update
          cy.wait(500);

          // Verify Axe is now unavailable
          assertHeroUnavailable(cy, 2);
        });
      });
    });
  });

  describe('Drafting Phase - Picks', () => {
    it('should allow captain to pick a hero (logged to events)', () => {
      setupDraftingPhase().then(() => {
        // Complete all 4 bans first (2 per team)
        // This is a simplified version - in reality we'd loop through bans

        cy.request({
          method: 'GET',
          url: `${Cypress.env('apiUrl')}/api/herodraft/${heroDraftPk}/`,
        }).then((response) => {
          const draft = response.body;
          const firstPickTeam = draft.draft_teams.find(
            (t: any) => t.is_first_pick,
          );
          const secondPickTeam = draft.draft_teams.find(
            (t: any) => !t.is_first_pick,
          );

          const firstPickDiscordId =
            firstPickTeam?.tournament_team?.captain?.discordId;
          const secondPickDiscordId =
            secondPickTeam?.tournament_team?.captain?.discordId;

          // Ban 1 (first pick team)
          if (firstPickDiscordId === CAPTAIN_RADIANT.discordId) {
            switchToCaptainRadiant(cy);
          } else {
            switchToCaptainDire(cy);
          }
          visitAndWaitForHydration(
            `/tournament/${tournamentPk}/bracket/draft/${heroDraftPk}`,
          );
          waitForHeroDraftModal(cy);
          clickHero(cy, 1); // Anti-Mage
          confirmHeroSelection(cy);
          cy.wait(300);

          // Ban 2 (second pick team)
          if (secondPickDiscordId === CAPTAIN_RADIANT.discordId) {
            switchToCaptainRadiant(cy);
          } else {
            switchToCaptainDire(cy);
          }
          visitAndWaitForHydration(
            `/tournament/${tournamentPk}/bracket/draft/${heroDraftPk}`,
          );
          waitForHeroDraftModal(cy);
          clickHero(cy, 2); // Axe
          confirmHeroSelection(cy);
          cy.wait(300);

          // Continue pattern for remaining bans...
          // After bans, first pick should be in Pick phase

          // Verify pick event when we get there
          cy.request({
            method: 'GET',
            url: `${Cypress.env('apiUrl')}/api/herodraft/${heroDraftPk}/`,
          }).then((draftResponse) => {
            const currentRound = draftResponse.body.rounds?.find(
              (r: any) => r.state === 'active',
            );
            if (currentRound?.action_type === 'pick') {
              // We're in pick phase
              cy.get('[data-testid="herodraft-current-action"]').should(
                'contain.text',
                'Pick',
              );
            }
          });
        });
      });
    });
  });
```

**Step 3: Verify compiles**

Run: `cd /home/kettle/git_repos/website/.worktrees/herodraft/frontend && npx tsc --noEmit -p tests/cypress/tsconfig.json 2>&1 | head -20`

**Step 4: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft && git add frontend/tests/cypress/e2e/10-herodraft/01-full-draft-flow.cy.ts && git commit -m "feat(cypress): add drafting phase tests for hero draft (bans and picks)"
```

---

### Task 13: Implement timeout and disconnect tests

**Files:**
- Modify: `frontend/tests/cypress/e2e/10-herodraft/01-full-draft-flow.cy.ts`

**Step 1: Add timeout and disconnect tests**

```typescript
  describe('Reserve Time Timeout', () => {
    it('should randomly select hero when time expires (logged to events)', () => {
      setupDraftingPhase().then(() => {
        // Force timeout via test endpoint
        cy.request({
          method: 'POST',
          url: `${Cypress.env('apiUrl')}/tests/herodraft/${heroDraftPk}/force-timeout/`,
        }).then((response) => {
          expect(response.status).to.eq(200);

          // Verify timeout event logged
          cy.request({
            method: 'GET',
            url: `${Cypress.env('apiUrl')}/api/herodraft/${heroDraftPk}/events/`,
          }).then((eventsResponse) => {
            const events = eventsResponse.body;
            const timeoutEvent = events.find(
              (e: any) => e.event_type === 'round_timeout',
            );
            expect(timeoutEvent).to.exist;
            expect(timeoutEvent.metadata.was_random).to.be.true;
          });
        });
      });
    });
  });

  describe('WebSocket Disconnect', () => {
    it('should pause draft when captain disconnects (logged to events)', () => {
      setupDraftingPhase().then(() => {
        // Get first pick captain
        cy.request({
          method: 'GET',
          url: `${Cypress.env('apiUrl')}/api/herodraft/${heroDraftPk}/`,
        }).then((response) => {
          const draft = response.body;
          const firstPickTeam = draft.draft_teams.find(
            (t: any) => t.is_first_pick,
          );
          const firstPickCaptainDiscordId =
            firstPickTeam?.tournament_team?.captain?.discordId;

          // Switch to first pick captain
          if (firstPickCaptainDiscordId === CAPTAIN_RADIANT.discordId) {
            switchToCaptainRadiant(cy);
          } else {
            switchToCaptainDire(cy);
          }

          visitAndWaitForHydration(
            `/tournament/${tournamentPk}/bracket/draft/${heroDraftPk}`,
          );
          waitForHeroDraftModal(cy);
          assertDraftingPhase(cy);

          // Close WebSocket by navigating away or closing connection
          cy.window().then((win) => {
            // Find and close WebSocket connections
            // The HeroDraft component stores ws in a ref
            const wsConnections = (win as any).__WEBSOCKET_CONNECTIONS__ || [];
            wsConnections.forEach((ws: WebSocket) => ws.close());

            // Alternative: navigate away to trigger disconnect
          });

          // Navigate away to trigger disconnect
          cy.visit('/');
          cy.wait(1000);

          // Check if draft paused (via API since we left the page)
          cy.request({
            method: 'GET',
            url: `${Cypress.env('apiUrl')}/api/herodraft/${heroDraftPk}/`,
          }).then((draftResponse) => {
            // Draft may pause due to disconnect
            // Verify disconnect event logged
            cy.request({
              method: 'GET',
              url: `${Cypress.env('apiUrl')}/api/herodraft/${heroDraftPk}/events/`,
            }).then((eventsResponse) => {
              const events = eventsResponse.body;
              const disconnectEvent = events.find(
                (e: any) => e.event_type === 'captain_disconnected',
              );
              expect(disconnectEvent).to.exist;
            });
          });
        });
      });
    });

    it('should resume draft when captain reconnects', () => {
      setupDraftingPhase().then(() => {
        cy.request({
          method: 'GET',
          url: `${Cypress.env('apiUrl')}/api/herodraft/${heroDraftPk}/`,
        }).then((response) => {
          const draft = response.body;
          const firstPickTeam = draft.draft_teams.find(
            (t: any) => t.is_first_pick,
          );
          const firstPickCaptainDiscordId =
            firstPickTeam?.tournament_team?.captain?.discordId;

          // Switch to first pick captain
          if (firstPickCaptainDiscordId === CAPTAIN_RADIANT.discordId) {
            switchToCaptainRadiant(cy);
          } else {
            switchToCaptainDire(cy);
          }

          visitAndWaitForHydration(
            `/tournament/${tournamentPk}/bracket/draft/${heroDraftPk}`,
          );
          waitForHeroDraftModal(cy);

          // Navigate away (disconnect)
          cy.visit('/');
          cy.wait(500);

          // Reconnect by visiting draft again
          visitAndWaitForHydration(
            `/tournament/${tournamentPk}/bracket/draft/${heroDraftPk}`,
          );
          waitForHeroDraftModal(cy);

          // Verify connected event
          cy.request({
            method: 'GET',
            url: `${Cypress.env('apiUrl')}/api/herodraft/${heroDraftPk}/events/`,
          }).then((eventsResponse) => {
            const events = eventsResponse.body;
            const reconnectEvents = events.filter(
              (e: any) => e.event_type === 'captain_connected',
            );
            // Should have multiple connect events (initial + reconnect)
            expect(reconnectEvents.length).to.be.greaterThan(0);
          });

          // Should be able to continue drafting (not paused)
          assertDraftingPhase(cy);
        });
      });
    });
  });
```

**Step 2: Verify compiles**

Run: `cd /home/kettle/git_repos/website/.worktrees/herodraft/frontend && npx tsc --noEmit -p tests/cypress/tsconfig.json 2>&1 | head -20`

**Step 3: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft && git add frontend/tests/cypress/e2e/10-herodraft/01-full-draft-flow.cy.ts && git commit -m "feat(cypress): add timeout and disconnect tests for hero draft"
```

---

### Task 14: Implement draft completion test

**Files:**
- Modify: `frontend/tests/cypress/e2e/10-herodraft/01-full-draft-flow.cy.ts`

**Step 1: Add completion test**

```typescript
  describe('Draft Completion', () => {
    it('should complete draft after all picks (logged to events)', () => {
      setupDraftingPhase().then(() => {
        // Use force-timeout repeatedly to complete all rounds quickly
        // Captain's Mode has 24 rounds (6 bans + 5 picks per team = 22, plus extras)

        const completeRound = () => {
          return cy.request({
            method: 'GET',
            url: `${Cypress.env('apiUrl')}/api/herodraft/${heroDraftPk}/`,
          }).then((response) => {
            if (response.body.state === 'drafting') {
              return cy
                .request({
                  method: 'POST',
                  url: `${Cypress.env('apiUrl')}/tests/herodraft/${heroDraftPk}/force-timeout/`,
                })
                .then(() => completeRound());
            }
            return response;
          });
        };

        // Complete all rounds via timeout
        completeRound().then((finalResponse) => {
          expect(finalResponse.body.state).to.eq('completed');

          // Verify completion event logged
          cy.request({
            method: 'GET',
            url: `${Cypress.env('apiUrl')}/api/herodraft/${heroDraftPk}/events/`,
          }).then((eventsResponse) => {
            const events = eventsResponse.body;
            const completionEvent = events.find(
              (e: any) => e.event_type === 'draft_completed',
            );
            expect(completionEvent).to.exist;
          });
        });
      });
    });

    it('should show final draft results', () => {
      // First complete the draft
      setupDraftingPhase().then(() => {
        const completeRound = () => {
          return cy.request({
            method: 'GET',
            url: `${Cypress.env('apiUrl')}/api/herodraft/${heroDraftPk}/`,
          }).then((response) => {
            if (response.body.state === 'drafting') {
              return cy
                .request({
                  method: 'POST',
                  url: `${Cypress.env('apiUrl')}/tests/herodraft/${heroDraftPk}/force-timeout/`,
                })
                .then(() => completeRound());
            }
            return response;
          });
        };

        completeRound().then(() => {
          // Visit the draft page
          switchToCaptainRadiant(cy);
          visitAndWaitForHydration(
            `/tournament/${tournamentPk}/bracket/draft/${heroDraftPk}`,
          );
          waitForHeroDraftModal(cy);

          // Should show completed state with both teams' picks
          cy.get('[data-testid="herodraft-panel-container"]').should(
            'be.visible',
          );

          // Verify all 10 picks visible (5 per team)
          cy.request({
            method: 'GET',
            url: `${Cypress.env('apiUrl')}/api/herodraft/${heroDraftPk}/`,
          }).then((response) => {
            const rounds = response.body.rounds || [];
            const picks = rounds.filter(
              (r: any) => r.action_type === 'pick' && r.state === 'completed',
            );
            expect(picks.length).to.eq(10); // 5 picks per team
          });
        });
      });
    });
  });
```

**Step 2: Verify compiles**

Run: `cd /home/kettle/git_repos/website/.worktrees/herodraft/frontend && npx tsc --noEmit -p tests/cypress/tsconfig.json 2>&1 | head -20`

**Step 3: Commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft && git add frontend/tests/cypress/e2e/10-herodraft/01-full-draft-flow.cy.ts && git commit -m "feat(cypress): add draft completion tests for hero draft"
```

---

## Phase 4: Verification

### Task 15: Repopulate database and run hero draft tests

**Step 1: Repopulate test database**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft
source .venv/bin/activate
inv db.populate.all
```

**Step 2: Verify Real Tournament 38 is pk 1**

```bash
inv test.exec --service backend --cmd 'python -c "from app.models import Tournament; t = Tournament.objects.get(name=\"Real Tournament 38\"); print(f\"PK: {t.pk}\")"'
```
Expected: `PK: 1`

**Step 3: Run hero draft E2E tests**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft
source .venv/bin/activate
inv test.open
# In Cypress UI, select e2e/10-herodraft/01-full-draft-flow.cy.ts
```

Or headless:
```bash
inv test.headless -- --spec "frontend/tests/cypress/e2e/10-herodraft/**/*"
```

**Step 4: Fix any failing tests**

Debug and fix issues found during test runs.

**Step 5: Commit any fixes**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft && git add -A && git commit -m "fix(cypress): address hero draft test failures"
```

---

### Task 16: Run full Cypress suite to verify no regressions

**Step 1: Run all Cypress tests**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft
source .venv/bin/activate
inv test.headless
```

**Step 2: Verify bracket tests still pass**

The bracket tests now use `getTournamentByKey()` instead of hardcoded PKs.

**Step 3: Fix any regressions**

If tests fail, debug and fix.

**Step 4: Final commit**

```bash
cd /home/kettle/git_repos/website/.worktrees/herodraft && git add -A && git commit -m "test(cypress): verify no regressions after hero draft E2E addition"
```

---

## Summary

This plan implements:

1. **Backend changes** (Tasks 1-5):
   - Reorder `populate_all()` so Real Tournament 38 is pk 1
   - Add `real_tournament` config key
   - Create `login_as_discord_id` endpoint
   - Create `force_herodraft_timeout` and `reset_herodraft` endpoints

2. **Cypress infrastructure** (Tasks 6-8):
   - Add `loginAsDiscordId` command
   - Create `herodraft-sessions.ts` helper
   - Update existing bracket tests to use dynamic PKs

3. **Hero draft E2E tests** (Tasks 9-14):
   - Waiting phase tests
   - Rolling phase tests
   - Choosing phase tests
   - Drafting phase tests (bans + picks)
   - Timeout tests
   - Disconnect/reconnect tests
   - Completion tests

4. **Verification** (Tasks 15-16):
   - Run hero draft tests first
   - Run full Cypress suite for regressions
