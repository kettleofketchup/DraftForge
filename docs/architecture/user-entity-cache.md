# User Entity Cache

The user entity cache is a normalized caching layer that separates **core user identity** from **context-scoped data** (org MMR, league MMR). It solves the problem of the same user appearing across multiple orgs, leagues, and tournaments with different MMR values in each context.

## Problem

A single user can belong to multiple organizations and leagues, each with a different MMR. Without normalization, user data is duplicated across every tournament, team, and draft response — inflating payloads and causing stale data when one copy is updated but others are not.

## Architecture Overview

```mermaid
flowchart LR
    subgraph Backend
        API[REST API / WebSocket]
        Slim[Slim Serializers<br/>UserPkField]
        Dict["_users dict<br/>{pk: full user}"]
    end

    subgraph Frontend
        Hydrate[hydrateTournament]
        Cache[UserCacheStore<br/>Entity Adapter]
        Components[React Components]
    end

    API --> Slim --> Dict
    Dict -->|JSON response| Hydrate
    Hydrate -->|full objects| Components
    Hydrate -->|upsert| Cache
    Cache -->|getById / isStale| Components
```

The pattern has three layers:

1. **Backend slim serializers** — replace full user objects with integer PKs, plus a deduplicated `_users` sidecar dict
2. **Frontend hydration** — resolves PK references back to full user objects for component consumption
3. **Entity cache** — normalized Zustand store with org/league-scoped MMR and staleness tracking

---

## Backend: Slim Serializers

### UserPkField

A custom DRF field that serializes user relationships as just their `pk`:

```python
# backend/app/serializers.py
class UserPkField(serializers.RelatedField):
    def to_representation(self, value):
        if value is None:
            return None
        return value.pk
```

### Slim Serializer Variants

Each serializer that includes user references has a `Slim` variant:

```python
class TeamSerializerSlim(TeamSerializerForTournament):
    """User fields as pk-only integers."""
    members = UserPkField(many=True, read_only=True)
    captain = UserPkField()
    deputy_captain = UserPkField()
    dropin_members = UserPkField(many=True, read_only=True)
    left_members = UserPkField(many=True, read_only=True)
```

Similarly for `DraftSerializerSlim`, `DraftRoundSerializerSlim`, and `TournamentSerializerBase`.

### The `_users` Sidecar Dict

Full user data is collected once and attached as `_users` on the response:

```python
def build_users_dict(tournament):
    """Build a deduplicated {pk: serialized_user} dict for a tournament."""
    seen_pks = collect_tournament_user_pks(tournament)
    user_qs = CustomUser.objects.filter(pk__in=seen_pks).select_related("positions")
    return {u["pk"]: u for u in _serialize_users_with_mmr(user_qs, tournament)}
```

This is injected in views, consumers, and broadcast functions:

```python
data = TournamentSerializerSlim(tournament).data
data["_users"] = build_users_dict(tournament)
```

### Resulting API Shape

```json
{
  "pk": 1,
  "name": "Weekly Tournament",
  "users": [101, 102, 103],
  "teams": [
    {
      "pk": 10,
      "captain": 101,
      "members": [101, 102],
      "deputy_captain": null
    }
  ],
  "_users": {
    "101": {
      "pk": 101, "username": "alice", "mmr": 2500,
      "orgUserPk": 50, "league_mmr": 2400
    },
    "102": {
      "pk": 102, "username": "bob", "mmr": 2800,
      "orgUserPk": 51, "league_mmr": 2700
    },
    "103": {
      "pk": 103, "username": "charlie", "mmr": 3000,
      "orgUserPk": 52, "league_mmr": 2900
    }
  }
}
```

Each user appears exactly once in `_users`, regardless of how many teams/rounds reference them.

### Org-Scoped MMR Serialization

When a tournament belongs to a league (and therefore an org), users are serialized with org-scoped MMR via `OrgUserSerializer`:

```python
def _serialize_users_with_mmr(users_qs, tournament, *, game_type=None, fresh=False):
    org = _tournament_organization(tournament, fresh=fresh)
    if not org:
        return TournamentUserSerializer(users_qs, many=True).data
    game = game_type or game_for_tournament(tournament)
    org_users = with_user_profiles(
        OrgUser.objects.filter(user__in=users_qs, organization=org), "user", dota=True
    ).prefetch_related(..., game_mmrs_prefetch(fresh=fresh))
    return OrgUserSerializer(
        org_users, many=True, context={"league_id": ..., "game_type": game}
    ).data
```

Org MMR is stored per game (`OrgUserGameMmr`, see [Org MMR per game](../features/org-mmr.md)).
The serializer resolves `mmr` for the context game and must have the `game_mmrs` rows
prefetched (`game_mmrs_prefetch()`); an unprefetched read logs `org_mmr_unprefetched`
and raises in tests.

The `OrgUserSerializer` includes:

- `pk` — the `CustomUser.pk` (user identity)
- `orgUserPk` — the `OrgUser.pk` (needed for org-scoped PATCH)
- `mmr` — org MMR for the context game (the tournament's game; Dota 2 when there is none)
- `mmr_game_type` — the game `mmr` was resolved for
- `game_mmrs` — `{"<game_type>": mmr}` for every game, only when the context sets `include_game_mmrs` (the gated org users endpoint and PATCH response). Tournament, team and draft payloads never carry it
- `league_mmr` — league-scoped MMR snapshot from `LeagueUser.mmr`

---

## Frontend: Hydration

### `hydrateTournament()`

Resolves PK-only references back to full user objects so components don't need to change:

```typescript
// frontend/app/lib/hydrateTournament.ts
export function hydrateTournament(
  raw: TournamentType & { _users?: Record<number, unknown> },
): TournamentType {
  const map = raw._users as UsersMap | undefined;
  if (!map) return raw;

  return {
    ...raw,
    users: resolveArray(raw.users, map),
    captains: resolveArray(raw.captains, map),
    teams: raw.teams?.map((t) => hydrateTeam(t, map)),
    games: raw.games?.map((g) => /* hydrate teams in game */),
    draft: raw.draft ? hydrateDraftFields(raw.draft, map) : raw.draft,
  } as TournamentType;
}
```

The `resolve()` function handles mixed data — if a reference is already an object it passes through, if it's a number it looks up the `_users` map:

```typescript
function resolve(ref: unknown, map: UsersMap): unknown {
  if (ref == null) return ref;
  if (typeof ref === 'number') return map[ref] ?? { pk: ref };
  return ref;
}
```

A companion `hydrateDraft()` function handles standalone draft responses.

---

## Frontend: Entity Cache

### Entity Adapter

A generic, reusable adapter for any entity type with a `pk: number` field:

```typescript
// frontend/app/lib/entityAdapter.ts
interface EntityState<T> {
  entities: Record<number, T>;
  indexes: Record<string, Record<string | number, number>>;
}
```

Key features:

- **Schema-driven change detection** — only checks fields defined in the Zod schema
- **Lazy allocation** — `upsertMany()` only spreads state when a change is detected
- **Reference preservation** — unchanged entities keep their object identity (prevents React re-renders)
- **Secondary indexes** — fast O(1) lookups by Discord ID, Steam Account ID, etc.

```typescript
const adapter = createEntityAdapter<UserEntry>({
  schema: CoreUserSchema,
  indexes: [
    { name: 'byDiscordId', key: 'discordId' },
    { name: 'bySteamAccountId', key: 'steam_account_id' },
  ],
});
```

### UserEntry Type

Separates core identity from context-scoped data:

```typescript
// frontend/app/store/userCacheTypes.ts
interface UserEntry {
  // Core identity (stable across all contexts)
  pk: number;
  username: string;
  avatar?: string | null;
  nickname?: string | null;
  steam_account_id?: number | null;
  discordId?: string | null;
  // ... other core fields

  // Context-scoped data (keyed by org/league id)
  orgData: Record<number, OrgUserData>;
  leagueData: Record<number, LeagueUserData>;

  // Staleness tracking
  _fetchedAt: number;
}

interface OrgUserData {
  id: number;                                  // OrgUser.pk (for PATCH operations)
  mmrs: Partial<Record<GameTypeValue, number>>; // Org MMR per game
  _fetchedAt: number;
}

interface LeagueUserData {
  id: number;       // LeagueUser.pk
  mmr: number;      // League-scoped MMR snapshot
  _fetchedAt: number;
}
```

### UserCacheStore

A Zustand store built on the entity adapter with custom scoped-data handling:

```typescript
// frontend/app/store/userCacheStore.ts
export const useUserCacheStore = create<UserCacheState>()(
  devtools((set, get) => ({
    ...userAdapter.getInitialState(),
    staleAfterMs: 5 * 60 * 1000, // 5 minutes

    upsert(incoming, context) { /* ... */ },
    remove(pk) { /* ... */ },
    getById(pk) { return get().entities[pk]; },
    getByDiscordId(discordId) { /* index lookup */ },
    getBySteamAccountId(id) { /* index lookup */ },
    isStale(pk, context) { /* checks core + scoped staleness */ },
    reset() { /* clears all entries */ },
  }))
);
```

!!! warning "Custom Upsert Logic"
    The store's `upsert()` method **bypasses** `adapter.upsertMany()` because the adapter only checks core keys for changes. Org/league MMR updates would be silently dropped. Instead, `upsert()` uses a custom `hasScopedChanged()` function that checks both core fields and scoped data.

### UpsertContext

When upserting users, a context object tells the cache which scoped data is being provided:

```typescript
interface UpsertContext {
  orgId?: number;
  leagueId?: number;
}

// Example: upserting users from an org page
useUserCacheStore.getState().upsert(users, { orgId: 5 });

// Example: upserting users from a league page
useUserCacheStore.getState().upsert(users, { orgId: 5, leagueId: 3 });
```

### Per-game org MMR

`OrgUserData.mmrs` holds one value per game. On upsert with an `orgId`:

- if the payload has `game_mmrs` (org users endpoint, PATCH response, gated signups),
  every game is taken from it;
- otherwise a flat `mmr` is filed under `mmr_game_type`, or Dota 2 when that is missing;
- the result is **merged per game** into the existing entry when the `OrgUser` id is the
  same, so a Deadlock tournament payload never erases the cached Dota value (and the
  reverse).

`hasScopedChanged()` compares each game. Components read a value for an explicit game:

```typescript
import { selectOrgMmr, useOrgMmr } from '~/store/selectOrgMmr';

const mmr = useOrgMmr(user.pk, orgId, toGameType(tournament.game_type));
```

There is no game-less accessor: every reader chooses a game.

### Staleness Tracking

Each entry tracks when its data was fetched. Both core and scoped data have independent timestamps:

```typescript
isStale(pk, context) {
  const entry = get().entities[pk];
  if (!entry) return true;

  const now = Date.now();
  const staleMs = get().staleAfterMs;

  // Core data stale?
  if (now - entry._fetchedAt > staleMs) return true;

  // Org-scoped data stale?
  if (context?.orgId) {
    const orgEntry = entry.orgData[context.orgId];
    if (!orgEntry || now - orgEntry._fetchedAt > staleMs) return true;
  }

  // League-scoped data stale?
  if (context?.leagueId) {
    const leagueEntry = entry.leagueData[context.leagueId];
    if (!leagueEntry || now - leagueEntry._fetchedAt > staleMs) return true;
  }

  return false;
}
```

### Zod Schemas

Two schemas define the canonical user shape:

```typescript
// frontend/app/components/user/schemas.ts

// Full schema — includes context-scoped fields from API responses
const UserSchema = z.object({
  pk: z.number().min(0).optional(),
  username: z.string().min(2).max(100),
  mmr: z.number().min(0).nullable().optional(),         // Org MMR for mmr_game_type
  mmr_game_type: z.number().nullable().optional(),
  game_mmrs: z.record(z.string(), z.number()).nullable().optional(), // gated payloads only
  league_mmr: z.number().min(0).nullable().optional(),  // League MMR
  orgUserPk: z.number().min(0).optional(),              // OrgUser.pk
  // ... other fields
});

// Core schema — omits context-scoped fields; used for change detection
const CoreUserSchema = UserSchema.omit({
  orgUserPk: true,
  mmr: true,
  game_mmrs: true,
  mmr_game_type: true,
  league_mmr: true,
}).extend({ pk: z.number() }); // pk required in cache
```

The entity adapter uses `CoreUserSchema` to determine which fields to compare — context-scoped fields (`mmr`, `mmr_game_type`, `game_mmrs`, `league_mmr`, `orgUserPk`) are handled separately in `orgData`/`leagueData`.

---

## Data Flow

```mermaid
sequenceDiagram
    participant C as Component
    participant S as UserStore
    participant API as Backend API
    participant Cache as UserCacheStore

    C->>S: getCurrentTournament()
    S->>API: GET /api/tournament/1/
    API-->>S: {users: [1,2,3], _users: {1:{...}, 2:{...}, 3:{...}}}
    S->>S: hydrateTournament(response)
    S->>Cache: upsert(hydratedUsers, {orgId, leagueId})
    S-->>C: tournament with full user objects

    Note over C,Cache: Later, on the org page...
    C->>Cache: getById(userPk)
    Cache-->>C: UserEntry with orgData[orgId].mmrs[game]
    C->>Cache: isStale(userPk, {orgId: 5})
    Cache-->>C: false (within 5min window)
```

---

## File Reference

### Backend

| File | Purpose |
|------|---------|
| `backend/app/serializers.py` | `UserPkField` |
| `backend/tournament/serializers/*.py` | Slim serializers; `build_users_dict()` in `users.py` |
| `backend/org/serializers.py` | `OrgUserSerializer` (org-scoped MMR + `orgUserPk`) |
| `backend/org/mmr.py` | Per-game org MMR reads, writes and prefetch |
| `backend/league/serializers.py` | `LeagueUserSerializer` (league-scoped MMR) |
| `backend/tournament/views/*.py`, `backend/draft/views/team_api.py` | Inject `_users` dict on tournament/draft GET responses |
| `backend/draft/consumers/team.py` | Injects `_users` dict on team-draft WebSocket state (via `draft/services/team_state.py`) |
| `backend/draft/services/team_broadcast.py` | Injects `_users` dict on team-draft broadcast events (via `draft/services/team_state.py`) |

### Frontend

| File | Purpose |
|------|---------|
| `frontend/app/lib/entityAdapter.ts` | Generic entity adapter (schema-driven, indexed) |
| `frontend/app/lib/entityAdapter.test.ts` | Unit tests for the adapter |
| `frontend/app/lib/hydrateTournament.ts` | Resolves PK references using `_users` dict |
| `frontend/app/store/userCacheStore.ts` | Zustand store with scoped upsert and staleness |
| `frontend/app/store/userCacheTypes.ts` | `UserEntry`, `OrgUserData`, `LeagueUserData`, `UpsertContext` |
| `frontend/app/store/selectOrgMmr.ts` | `selectOrgMmr` / `useOrgMmr`: org MMR for one game |
| `frontend/app/components/user/schemas.ts` | `UserSchema`, `CoreUserSchema` (Zod) |
