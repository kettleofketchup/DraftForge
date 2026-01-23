# Captain Draft Pick Feature - Design Document

**Status:** Completed

**Date:** 2026-01-07
**Status:** Draft
**Author:** Claude (with user guidance)

## Overview

Enable captains to pick their own team members during an active draft, with UI notifications and comprehensive testing infrastructure.

## Goals

1. Allow captains to make picks when it's their turn (not just staff)
2. Notify captains of active drafts via flashing icons
3. Auto-open draft modal when captain visits during their turn
4. Create robust test infrastructure with dedicated test tournaments
5. Enable fast, independent Cypress tests

## Non-Goals

- Changing the draft algorithm (snake/normal)
- Real-time WebSocket updates (keeping polling approach)
- Mobile app notifications

---

## Architecture

### Backend Changes

#### 1. Modified Permission for Pick Endpoint

**File:** `backend/app/functions/tournament.py`

Current `pick_player_for_round` requires `IsStaff`. Modify to allow captain OR staff:

```python
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def pick_player_for_round(request):
    serializer = PickPlayerForRound(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)

    draft_round_pk = serializer.validated_data["draft_round_pk"]
    user_pk = serializer.validated_data["user_pk"]

    try:
        draft_round = DraftRound.objects.get(pk=draft_round_pk)
    except DraftRound.DoesNotExist:
        return Response({"error": "Draft round not found"}, status=404)

    # Authorization: staff OR captain for this round
    is_staff = request.user.is_staff
    is_captain = draft_round.captain == request.user

    if not (is_staff or is_captain):
        return Response(
            {"error": "Only staff or the captain for this round can pick"},
            status=403
        )

    # ... rest of existing logic unchanged
```

#### 2. New Endpoint: Active Draft Check

**File:** `backend/app/functions/tournament.py`

```python
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_active_draft_for_user(request):
    """Returns active draft info if user is a captain with a pending pick."""
    pending_round = DraftRound.objects.filter(
        captain=request.user,
        choice__isnull=True,
        draft__tournament__state="in_progress"
    ).select_related('draft__tournament').first()

    if pending_round:
        return Response({
            "has_active_turn": True,
            "tournament_pk": pending_round.draft.tournament.pk,
            "tournament_name": pending_round.draft.tournament.name,
            "draft_round_pk": pending_round.pk,
            "pick_number": pending_round.pick_number,
        })
    return Response({"has_active_turn": False})
```

**URL:** `GET /api/active-draft-for-user/`

#### 3. Test-Only Login Endpoint

**File:** `backend/tests/views.py`

```python
from django.conf import settings

@api_view(["POST"])
@permission_classes([AllowAny])
def test_login_as_user(request):
    """TEST ONLY: Login as any user by ID. Returns 404 if not in test mode."""
    if not getattr(settings, 'TEST_MODE', False):
        return Response(status=404)

    user_pk = request.data.get('user_pk')
    if not user_pk:
        return Response({"error": "user_pk required"}, status=400)

    try:
        user = CustomUser.objects.get(pk=user_pk)
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        return Response({"success": True, "user": UserSerializer(user).data})
    except CustomUser.DoesNotExist:
        return Response({"error": "User not found"}, status=404)
```

**Security:** Only available when `TEST_MODE=true` environment variable is set.

**URL:** `POST /api/test/login-as/` (conditionally registered)

#### 4. Test Tournament Lookup Endpoint

**File:** `backend/tests/views.py`

```python
@api_view(["GET"])
@permission_classes([AllowAny])
def get_tournament_by_key(request, key: str):
    """TEST ONLY: Get tournament by test config key."""
    if not getattr(settings, 'TEST_MODE', False):
        return Response(status=404)

    tournament = Tournament.objects.filter(name=TEST_KEY_TO_NAME[key]).first()
    if not tournament:
        return Response({"error": f"Tournament '{key}' not found"}, status=404)

    return Response(TournamentSerializer(tournament).data)
```

**URL:** `GET /api/test/tournament-by-key/<key>/`

---

### Frontend Changes

#### 1. Active Draft Hook

**File:** `frontend/app/hooks/useActiveDraft.ts`

```typescript
interface ActiveDraftInfo {
  has_active_turn: boolean;
  tournament_pk?: number;
  tournament_name?: string;
  draft_round_pk?: number;
  pick_number?: number;
}

export const useActiveDraft = () => {
  const currentUser = useUserStore((state) => state.currentUser);
  const [activeDraft, setActiveDraft] = useState<ActiveDraftInfo | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!currentUser?.pk) {
      setActiveDraft(null);
      setLoading(false);
      return;
    }

    const checkActiveDraft = async () => {
      try {
        const response = await axios.get('/api/active-draft-for-user/');
        setActiveDraft(response.data.has_active_turn ? response.data : null);
      } catch (err) {
        setActiveDraft(null);
      } finally {
        setLoading(false);
      }
    };

    checkActiveDraft();
    const interval = setInterval(checkActiveDraft, 5000);
    return () => clearInterval(interval);
  }, [currentUser?.pk]);

  return { activeDraft, hasActiveTurn: !!activeDraft?.has_active_turn, loading };
};
```

#### 2. Notification Badge Component

**File:** `frontend/app/components/draft/DraftNotificationBadge.tsx`

```typescript
export const DraftNotificationBadge: React.FC = () => {
  const { hasActiveTurn } = useActiveDraft();

  if (!hasActiveTurn) return null;

  return (
    <motion.div
      data-testid="draft-notification-badge"
      className="absolute -top-1 -right-1 w-4 h-4 bg-red-500 rounded-full"
      animate={{ scale: [1, 1.2, 1], opacity: [1, 0.7, 1] }}
      transition={{ duration: 1, repeat: Infinity }}
    />
  );
};
```

#### 3. Floating Draft Indicator

**File:** `frontend/app/components/draft/FloatingDraftIndicator.tsx`

```typescript
export const FloatingDraftIndicator: React.FC = () => {
  const { activeDraft, hasActiveTurn } = useActiveDraft();

  if (!hasActiveTurn || !activeDraft) return null;

  return (
    <motion.a
      data-testid="floating-draft-indicator"
      href={`/tournaments/${activeDraft.tournament_pk}?draft=open`}
      className="fixed bottom-6 right-6 z-50 bg-red-600 hover:bg-red-700
                 text-white px-4 py-3 rounded-full shadow-lg flex items-center gap-2"
      animate={{ scale: [1, 1.05, 1] }}
      transition={{ duration: 1.5, repeat: Infinity }}
    >
      <ClipboardPen className="w-5 h-5" />
      <span>Your turn to pick!</span>
    </motion.a>
  );
};
```

#### 4. Modified ChoosePlayerButton

**File:** `frontend/app/components/draft/buttons/choosePlayerButtons.tsx`

```typescript
export const ChoosePlayerButton: React.FC<{ user: UserType }> = ({ user }) => {
  const currentUser = useUserStore((state) => state.currentUser);
  const curDraftRound = useUserStore((state) => state.curDraftRound);
  const isStaff = useUserStore((state) => state.isStaff);

  const isCaptainForRound = currentUser?.pk === curDraftRound?.captain?.pk;
  const canPick = isStaff() || isCaptainForRound;
  const pickAlreadyMade = !!curDraftRound?.choice;

  if (!canPick) {
    return <AdminOnlyButton buttonTxt="Waiting for captain" />;
  }

  if (pickAlreadyMade) {
    return <Button disabled>Pick already made</Button>;
  }

  return (
    <AlertDialog>
      {/* ... existing dialog implementation ... */}
    </AlertDialog>
  );
};
```

#### 5. Turn Indicator Component

**File:** `frontend/app/components/draft/roundView/TurnIndicator.tsx`

```typescript
export const TurnIndicator: React.FC = () => {
  const currentUser = useUserStore((state) => state.currentUser);
  const curDraftRound = useUserStore((state) => state.curDraftRound);

  const isMyTurn = currentUser?.pk === curDraftRound?.captain?.pk;
  const captainName = curDraftRound?.captain?.username;

  return (
    <div className={`p-4 rounded-lg text-center ${
      isMyTurn ? 'bg-green-800 animate-pulse' : 'bg-base-200'
    }`}>
      {isMyTurn ? (
        <span className="text-lg font-bold">It's YOUR turn to pick!</span>
      ) : (
        <span>Waiting for {captainName} to pick...</span>
      )}
    </div>
  );
};
```

#### 6. Auto-Open Draft Modal

**File:** `frontend/app/pages/tournament/TournamentDetailPage.tsx`

Add logic to auto-open draft modal:

```typescript
const TournamentDetailPage: React.FC = () => {
  const { activeDraft } = useActiveDraft();
  const [searchParams] = useSearchParams();
  const tournamentPk = useParams().pk;

  // Auto-open if captain has active turn for THIS tournament, or URL param
  const shouldAutoOpen =
    (activeDraft?.tournament_pk === Number(tournamentPk)) ||
    searchParams.get('draft') === 'open';

  // ... pass shouldAutoOpen to DraftModal
};
```

---

### Test Infrastructure

#### 1. Pydantic Tournament Config

**File:** `backend/tests/helpers/tournament_config.py`

See Section 6 (Revised) for full implementation. Key features:

- `TestTournamentConfig` Pydantic model with typed fields
- Self-documenting descriptions for each field
- Methods: `create()`, `_create_teams()`, `_create_draft()`, `_create_bracket_games()`
- Pre-defined `TEST_TOURNAMENTS` list with 6 scenarios

#### 2. Steam Match Helper

**File:** `backend/tests/helpers/steam_match.py`

- `generate_unique_match_id(prefix)` - Ensures no duplicate match IDs
- `generate_steam_match(radiant, dire, radiant_win, duration, match_id)` - Creates Match with PlayerMatchStats
- `reset_match_id_tracker()` - Reset between test runs

#### 3. Cypress Commands

**File:** `frontend/tests/cypress/support/commands.ts`

- `cy.loginAsUser(pk)` - Test-only login
- `cy.loginAsTestUser()` - Login as pk=1
- `cy.loginAsStaff()` - Login as pk=2
- `cy.loginAsCaptain(tournamentKey)` - Login as first captain of tournament
- `cy.getTournamentByKey(key)` - Get tournament data by config key

#### 4. Cypress Test Files

```
frontend/tests/cypress/e2e/07-draft/
├── 01-captain-pick.cy.ts      # 5 tests
├── 02-notification.cy.ts       # 5 tests
├── 03-auto-open-modal.cy.ts    # 4 tests
├── 04-live-view.cy.ts          # 3 tests
└── 05-staff-pick.cy.ts         # 3 tests
```

#### 5. Invoke Tasks

**File:** `backend/tasks.py`

```python
@task
def test_run(c, spec=None):
    """Run Cypress tests with optional spec filter."""
    spec_map = {
        'drafts': 'tests/cypress/e2e/07-draft/**/*.cy.ts',
        'bracket': 'tests/cypress/e2e/04-tournament/**/*.cy.ts',
        'mobile': 'tests/cypress/e2e/06-mobile/**/*.cy.ts',
        'match': 'tests/cypress/e2e/05-match-stats/**/*.cy.ts',
    }
    # ... implementation
```

---

## Test Tournament Matrix

| Key | Name | Draft State | Picks | Bracket Games | Test User Captain | Primary Tests |
|-----|------|-------------|-------|---------------|-------------------|---------------|
| `draft_not_started` | Draft Not Started | not_started | 0 | 0 | No | Draft init UI |
| `draft_in_progress` | Draft In Progress | in_progress | 3 | 0 | No | Live view, navigation |
| `draft_captain_turn` | Captain Turn Test | in_progress | 0 | 0 | **Yes** | **Captain pick flow** |
| `draft_completed` | Draft Completed | completed | 16 | 0 | No | Roster display |
| `bracket_partial` | Bracket Partial | completed | 16 | 2 | No | Bracket progression |
| `bracket_complete` | Bracket Complete | completed | 16 | 6 | No | Final standings |

---

## File Changes Summary

### Backend (New Files)
- `backend/tests/helpers/tournament_config.py`
- `backend/tests/helpers/steam_match.py`
- `backend/tests/views.py` (test endpoints)

### Backend (Modified Files)
- `backend/app/functions/tournament.py` - Modified pick permissions, new endpoint
- `backend/backend/urls.py` - Conditional test URL registration
- `backend/backend/settings.py` - Add `TEST_MODE` flag
- `backend/tasks.py` - Add `test.run` task with spec filter

### Frontend (New Files)
- `frontend/app/hooks/useActiveDraft.ts`
- `frontend/app/components/draft/DraftNotificationBadge.tsx`
- `frontend/app/components/draft/FloatingDraftIndicator.tsx`
- `frontend/app/components/draft/roundView/TurnIndicator.tsx`
- `frontend/tests/cypress/e2e/07-draft/*.cy.ts` (5 files)

### Frontend (Modified Files)
- `frontend/app/components/draft/buttons/choosePlayerButtons.tsx`
- `frontend/app/components/draft/draftModal.tsx`
- `frontend/app/components/navbar/login.tsx`
- `frontend/app/pages/tournament/TournamentDetailPage.tsx`
- `frontend/app/root.tsx`
- `frontend/tests/cypress/support/commands.ts`

### Documentation (New Files)
- `docs/testing/test-tournaments.md`

---

## Security Considerations

1. **Test Login Endpoint:** Only available when `TEST_MODE=true`. Returns 404 otherwise (endpoint appears not to exist).

2. **Captain Pick Authorization:** Server-side check ensures `request.user == draft_round.captain` before allowing pick.

3. **No Token Exposure:** Using session-based auth, not exposing tokens to frontend.

---

## Implementation Order

1. Backend: Test infrastructure (helpers, test endpoints)
2. Backend: Modified pick endpoint with captain authorization
3. Backend: Active draft check endpoint
4. Frontend: `useActiveDraft` hook
5. Frontend: Notification components (badge + floating)
6. Frontend: Modified `ChoosePlayerButton`
7. Frontend: Auto-open modal logic
8. Cypress: Commands and test files
9. Documentation: Test tournament reference

---

## Open Questions

None - all clarified during design.
