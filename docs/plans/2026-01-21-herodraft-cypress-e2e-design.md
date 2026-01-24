# Hero Draft Cypress E2E Test Design

**Status:** Completed

## Overview

This test suite validates the complete hero draft (Captain's Mode) flow using Real Tournament 38's Winners Final game. It uses `cy.session()` for fast captain identity switching and tests all draft phases including edge cases like timeouts and disconnects.

## Goals

- Test the full hero draft lifecycle from creation to completion
- Verify all state transitions are logged to HeroDraftEvent
- Test edge cases: reserve time timeout, WebSocket disconnects
- Use stable Discord IDs for captain authentication (not PKs)
- Ensure Real Tournament 38 is pk 1 for consistent test data

## Architecture

### Tournament Data

Real Tournament 38's Winners Final game:
- **Radiant Captain**: vrm.mtl (Discord ID: 764290890617192469)
- **Dire Captain**: ethan0688_ (Discord ID: 1325607754177581066)

### Session Management

Single browser with `cy.session()` for fast captain swapping:
```
Captain1 → Ready → (switch session)
Captain2 → Ready → (both ready triggers rolling) → (switch)
Captain1 → Flip Coin → Winner makes choice → (switch)
Captain2 → Loser makes choice → (drafting starts) → (switch)
Captain1 → Ban → (switch) → Captain2 → Ban → ...etc
```

### Draft Flow

```
waiting_for_captains → rolling → choosing → drafting → completed
        ↓                ↓          ↓          ↓
   Both ready      Coin flip   Pick order   24 rounds
                               & side       (bans + picks)
```

## Backend Changes

### 1. Populate Function Reordering

Modify `populate_all()` in `backend/tests/populate.py`:

```python
def populate_all(force=False):
    """Run all population functions in the correct order."""
    populate_organizations_and_leagues(force)
    populate_users(force)
    populate_real_tournament_38(force)  # MOVED FIRST - gets pk 1
    populate_tournaments(force)          # Now starts at pk 2+
    populate_steam_matches(force)
    populate_bracket_linking_scenario(force)
```

### 2. Tournament Config Key

Add to `backend/tests/helpers/tournament_config.py`:

```python
TEST_KEY_TO_NAME["real_tournament"] = "Real Tournament 38"
```

### 3. New Test Auth Endpoint

Add to `backend/tests/test_auth.py`:

```python
@api_view(["POST"])
def login_as_discord_id(request):
    """Login as user by Discord ID (TEST ONLY)."""
    discord_id = request.data.get("discord_id")
    user = CustomUser.objects.filter(discordId=discord_id).first()
    if not user:
        return Response({"error": "User not found"}, status=404)
    login(request, user)
    return Response({"success": True, "user": UserSerializer(user).data})
```

URL: `POST /tests/login-as-discord/`

### 4. Test Endpoint for Force Timeout

Create `backend/tests/test_herodraft.py`:

```python
@api_view(["POST"])
def force_herodraft_timeout(request, draft_pk):
    """Force timeout on current round (TEST ONLY)."""
    draft = get_object_or_404(HeroDraft, pk=draft_pk)
    current_round = draft.rounds.filter(state="active").first()
    if current_round:
        from app.functions.herodraft import handle_timeout
        handle_timeout(draft, current_round)
    return Response(HeroDraftSerializer(draft).data)
```

URL: `POST /tests/herodraft/{draft_pk}/force-timeout/`

## Cypress Infrastructure Changes

### 1. New Custom Command

Add to `frontend/tests/cypress/support/commands.ts`:

```typescript
Cypress.Commands.add('loginAsDiscordId', (discordId: string) => {
  return cy.request({
    method: 'POST',
    url: `${Cypress.env('apiUrl')}/tests/login-as-discord/`,
    body: { discord_id: discordId },
    headers: { 'Content-Type': 'application/json' },
  });
});
```

### 2. Session-Based Captain Switching

Create `frontend/tests/cypress/helpers/herodraft-sessions.ts`:

```typescript
export const CAPTAIN_RADIANT = {
  discordId: '764290890617192469',
  username: 'vrm.mtl',
  sessionName: 'captain_radiant',
};

export const CAPTAIN_DIRE = {
  discordId: '1325607754177581066',
  username: 'ethan0688_',
  sessionName: 'captain_dire',
};

export const loginAsCaptain = (cy: Cypress.cy, captain: typeof CAPTAIN_RADIANT) => {
  cy.session(captain.sessionName, () => {
    cy.loginAsDiscordId(captain.discordId);
  });
};

export const switchToCaptainRadiant = (cy: Cypress.cy) => loginAsCaptain(cy, CAPTAIN_RADIANT);
export const switchToCaptainDire = (cy: Cypress.cy) => loginAsCaptain(cy, CAPTAIN_DIRE);
```

### 3. Update Existing Bracket Tests

Update tests to use `getTournamentByKey()` instead of hardcoded PKs:

```typescript
// Before
visitAndWaitForHydration('/tournament/1/games');

// After
cy.getTournamentByKey('completed_bracket').then((response) => {
  visitAndWaitForHydration(`/tournament/${response.body.pk}/games`);
});
```

## Test Cases

### File: `frontend/tests/cypress/e2e/10-herodraft/01-full-draft-flow.cy.ts`

#### Waiting Phase
- Create hero draft and show waiting state
- Captain Radiant ready up (logged to events)
- Captain Dire ready up (logged to events)
- Transition to rolling when both ready

#### Rolling Phase
- Show coin flip UI
- Captain triggers flip (logged to events)
- Display roll winner

#### Choosing Phase
- Roll winner chooses pick order or side
- Roll loser chooses remaining option (logged to events)
- Transition to drafting when both choices made

#### Drafting Phase - Bans
- Show first ban phase for correct captain
- Captain selects and confirms ban (logged to events)
- Banned hero marked as unavailable
- Alternate bans between captains

#### Drafting Phase - Picks
- Transition to pick phase after bans
- Captain picks hero (logged to events)
- Picked hero shown in draft panel

#### Reserve Time Timeout
- Randomly select hero when time expires (logged to events)

#### WebSocket Disconnect
- Pause draft when captain disconnects (logged to events)
- Resume draft when captain reconnects

#### Draft Completion
- Complete draft after all picks (logged to events)
- Show final draft results

## Event Verification

All major actions are verified by checking HeroDraftEvent records:

```typescript
const verifyDraftEvent = (cy: Cypress.cy, draftPk: number, eventType: string) => {
  cy.request({
    method: 'GET',
    url: `${Cypress.env('apiUrl')}/api/herodraft/${draftPk}/events/`,
  }).then((response) => {
    const events = response.body;
    const hasEvent = events.some((e: any) => e.event_type === eventType);
    expect(hasEvent).to.be.true;
  });
};
```

## Implementation Phases

### Phase 1: Backend Setup
1. Reorder `populate_all()` to run `populate_real_tournament_38()` first
2. Add `real_tournament` key to `TEST_KEY_TO_NAME`
3. Create `login_as_discord_id` test endpoint
4. Create `force_herodraft_timeout` test endpoint
5. Add URL routes for new test endpoints

### Phase 2: Cypress Infrastructure
1. Add `loginAsDiscordId` command to `commands.ts`
2. Create `herodraft-sessions.ts` helper with captain constants
3. Update existing bracket tests to use `getTournamentByKey()`

### Phase 3: Hero Draft Tests
1. Create `10-herodraft/01-full-draft-flow.cy.ts`
2. Implement waiting phase tests
3. Implement rolling phase tests
4. Implement choosing phase tests
5. Implement drafting phase tests (bans + picks)
6. Implement timeout test
7. Implement disconnect/pause test
8. Implement completion test

### Phase 4: Verification
1. Run `inv db.populate.all` to verify tournament ordering
2. Run hero draft tests specifically first
3. Run full Cypress suite to verify no regressions
