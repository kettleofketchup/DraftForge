# API Endpoints

All API endpoints are prefixed with `/api/`.

## Authentication

Authentication is handled via Discord OAuth through django-social-auth.

### Test Endpoints

For E2E testing, the following endpoints are available:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/tests/login-user/` | POST | Login as regular user |
| `/api/tests/login-staff/` | POST | Login as staff user |
| `/api/tests/login-admin/` | POST | Login as admin user |
| `/api/tests/login-as/` | POST | Login as any user by PK |
| `/api/tests/tournament-by-key/{key}/` | GET | Get tournament by test config key |

!!! warning "Test Only"
    These endpoints are only available in test/development environments.

#### Login As User

```bash
POST /api/tests/login-as/
Content-Type: application/json

{"user_pk": 123}
```

Returns user details and sets session cookies.

## Users

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/users/` | List users |
| GET | `/api/users/{id}/` | Get user details |
| PUT | `/api/users/{id}/` | Update user |

## Tournaments

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/tournaments/` | List tournaments |
| POST | `/api/tournaments/` | Create tournament |
| GET | `/api/tournaments/{id}/` | Get tournament |
| PUT | `/api/tournaments/{id}/` | Update tournament |
| DELETE | `/api/tournaments/{id}/` | Delete tournament |

## Teams

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/teams/` | List teams |
| POST | `/api/teams/` | Create team |
| GET | `/api/teams/{id}/` | Get team |

## Games

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/games/` | List games |
| POST | `/api/games/` | Create game |
| GET | `/api/games/{id}/` | Get game |

## Steam / League Stats

Endpoints for Steam integration and league statistics.

### Leaderboard

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/steam/leaderboard/` | Paginated league leaderboard |

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | int | 1 | Page number |
| `page_size` | int | 20 | Results per page |
| `sort_by` | string | `league_mmr` | Sort field: `league_mmr`, `games_played`, `win_rate`, `avg_kda` |
| `order` | string | `desc` | Sort order: `asc`, `desc` |

**Response:**

```json
{
  "count": 50,
  "next": "/api/steam/leaderboard/?page=2",
  "previous": null,
  "results": [
    {
      "user_id": 1,
      "username": "player1",
      "avatar": "https://...",
      "league_mmr": 3250,
      "mmr_adjustment": 150,
      "games_played": 25,
      "wins": 15,
      "losses": 10,
      "win_rate": 0.6,
      "avg_kda": 3.5,
      "avg_gpm": 450
    }
  ]
}
```

### League Stats

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/steam/league-stats/{user_id}/` | Get user's league stats | No |
| GET | `/api/steam/league-stats/me/` | Get current user's stats | Yes |

**Response:**

```json
{
  "user_id": 1,
  "username": "player1",
  "league_id": 1,
  "games_played": 25,
  "wins": 15,
  "losses": 10,
  "win_rate": 0.6,
  "avg_kills": 8.5,
  "avg_deaths": 4.2,
  "avg_assists": 12.3,
  "avg_kda": 3.5,
  "avg_gpm": 450,
  "avg_xpm": 520,
  "league_mmr": 3250
}
```

## Organizations

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/organizations/` | List organizations | No |
| POST | `/api/organizations/` | Create organization | Admin |
| GET | `/api/organizations/{id}/` | Get organization details | No |
| PUT | `/api/organizations/{id}/` | Update organization | Org Admin |
| DELETE | `/api/organizations/{id}/` | Delete organization | Admin |

**Query Parameters (list):**

| Parameter | Type | Description |
|-----------|------|-------------|
| `user` | int | Filter by user membership (admin or staff) |

**Response (detail):**

```json
{
  "id": 1,
  "name": "DTX Gaming",
  "description": "Dota 2 gaming organization",
  "logo": "https://...",
  "admins": [{ "id": 1, "username": "admin" }],
  "staff": [{ "id": 2, "username": "staff" }],
  "leagues": [{ "id": 1, "name": "Spring League" }],
  "league_count": 2,
  "tournament_count": 5
}
```

## Leagues

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/leagues/` | List leagues | No |
| POST | `/api/leagues/` | Create league | Yes |
| GET | `/api/leagues/{id}/` | Get league details | No |
| PUT | `/api/leagues/{id}/` | Update league | League Admin |
| DELETE | `/api/leagues/{id}/` | Delete league | League Admin |

**Query Parameters (list):**

| Parameter | Type | Description |
|-----------|------|-------------|
| `organization` | int | Filter by organization ID |

**Response (detail):**

```json
{
  "id": 1,
  "name": "Spring League 2024",
  "organization": { "id": 1, "name": "DTX Gaming" },
  "admins": [{ "id": 1, "username": "admin" }],
  "staff": [{ "id": 2, "username": "staff" }],
  "tournaments": [{ "id": 1, "name": "Week 1" }],
  "tournament_count": 4
}
```

## Drafts (Player Draft)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/drafts/` | List drafts |
| GET | `/api/drafts/{id}/` | Get draft details |
| PUT | `/api/drafts/{id}/` | Update draft (e.g., change style) |
| POST | `/api/tournaments/init-draft` | Initialize draft for tournament |
| POST | `/api/tournaments/pick_player` | Pick player for draft round |

### Draft Pick (Shuffle Draft)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/tournaments/{id}/draft/pick/` | Make a draft pick |

**Request Body:**
```json
{
  "player_id": 123
}
```

**Response (Shuffle Draft with tie):**
```json
{
  "success": true,
  "tournament": { ... },
  "next_pick": {
    "captain_id": 5,
    "team_id": 2,
    "team_name": "Team Beta",
    "team_mmr": 15400
  },
  "tie_resolution": {
    "tied_teams": [
      {"id": 1, "name": "Team Alpha", "mmr": 15400},
      {"id": 2, "name": "Team Beta", "mmr": 15400}
    ],
    "roll_rounds": [
      [{"team_id": 1, "roll": 4}, {"team_id": 2, "roll": 6}]
    ],
    "winner_id": 2
  }
}
```

!!! note "Shuffle Draft"
    The `next_pick` and `tie_resolution` fields only appear for shuffle draft style.
    For snake/normal drafts, pick order is predetermined.

### Pick Player (Captain Draft)

Allows staff or the current round's captain to pick a player:

```bash
POST /api/tournaments/pick_player
Content-Type: application/json

{
  "draft_round_pk": 123,
  "user_pk": 456
}
```

!!! note "Captain Permissions"
    Captains can pick players during their turn. Staff can pick for any captain.

## HeroDraft (Captain's Mode)

Hero draft endpoints for Dota 2 Captain's Mode pick/ban phase. All endpoints require authentication.

!!! info "WebSocket Support"
    HeroDraft also supports real-time updates via WebSocket at `/api/herodraft/{draft_pk}/`.
    The WebSocket broadcasts events like `draft_created`, `captain_ready`, `roll_result`, `choice_made`, `hero_selected`, and `draft_abandoned`.

### Create HeroDraft

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/games/{game_pk}/create-herodraft/` | Create a HeroDraft for a game |

Creates a new hero draft for a game. Returns existing draft if one already exists.

**Requirements:**

- Game must have both `radiant_team` and `dire_team` assigned
- Both teams must have captains assigned

**Response (201 Created / 200 OK if exists):**
```json
{
  "id": 1,
  "game": 5,
  "state": "waiting_for_captains",
  "draft_teams": [
    {
      "id": 1,
      "tournament_team": { ... },
      "is_ready": false,
      "is_connected": false,
      "is_first_pick": null,
      "is_radiant": null
    },
    { ... }
  ],
  "rounds": [],
  "roll_winner": null
}
```

### Get HeroDraft

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/herodraft/{draft_pk}/` | Get HeroDraft details |

Returns the current state of a hero draft.

### Set Captain Ready

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/herodraft/{draft_pk}/set-ready/` | Mark captain as ready |

Marks the authenticated user's team as ready. When both captains are ready, the draft transitions to "rolling" state.

**Requirements:**

- Draft must be in `waiting_for_captains` state
- User must be a captain in this draft

**Errors:**

- `403`: User is not a captain in this draft
- `400`: Invalid state for this operation

### Trigger Roll

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/herodraft/{draft_pk}/trigger-roll/` | Trigger dice roll |

Triggers the coin flip to determine which team chooses first (pick order or side).

**Requirements:**

- Draft must be in `rolling` state
- User must be a captain in this draft

**Response:**
Returns updated draft data with `roll_winner` set.

### Submit Choice

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/herodraft/{draft_pk}/submit-choice/` | Submit first pick choice |

Submit a choice for pick order or side. The roll winner chooses first, then the other team gets the remaining choice.

**Request Body:**
```json
{
  "choice_type": "pick_order",
  "value": "first"
}
```

| Field | Type | Values |
|-------|------|--------|
| `choice_type` | string | `"pick_order"` or `"side"` |
| `value` | string | For pick_order: `"first"` or `"second"`. For side: `"radiant"` or `"dire"` |

**Requirements:**

- Draft must be in `choosing` state
- User must be a captain in this draft
- Roll winner must choose first
- Choice must not already be made

### Submit Pick

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/herodraft/{draft_pk}/submit-pick/` | Submit hero pick/ban |

Submit a hero pick or ban for the current round.

**Request Body:**
```json
{
  "hero_id": 1
}
```

**Requirements:**

- Draft must be in `drafting` state
- User must be a captain in this draft
- Must be the user's turn to pick/ban
- Hero must be available (not already picked or banned)

**Errors:**

- `403`: User is not a captain or not their turn
- `400`: Invalid state, hero already picked, or invalid hero

### List Events

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/herodraft/{draft_pk}/list-events/` | List draft events |

Returns all events for a hero draft (for audit trail and replay).

**Response:**
```json
[
  {
    "id": 1,
    "event_type": "captain_connected",
    "draft_team": null,
    "metadata": { "created_by": 1 },
    "created_at": "2024-01-01T00:00:00Z"
  },
  {
    "id": 2,
    "event_type": "captain_ready",
    "draft_team": 1,
    "metadata": { "captain_id": 1 },
    "created_at": "2024-01-01T00:00:05Z"
  }
]
```

### List Available Heroes

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/herodraft/{draft_pk}/list-available-heroes/` | List available heroes |

Returns all hero IDs that are still available (not picked or banned).

**Response:**
```json
{
  "available_heroes": [1, 2, 3, 5, 7, 8, ...]
}
```

### Abandon Draft

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/herodraft/{draft_pk}/abandon/` | Abandon draft |

Abandon a hero draft. Can be called by a captain in the draft or an admin.

**Requirements:**

- Draft must not be in `completed` or `abandoned` state
- User must be a captain in this draft OR an admin

**Errors:**

- `403`: User not authorized to abandon this draft
- `400`: Draft already completed or abandoned

## Response Format

All responses follow this format:

```json
{
  "id": 1,
  "field": "value",
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:00:00Z"
}
```

## Error Responses

```json
{
  "detail": "Error message"
}
```

| Status | Description |
|--------|-------------|
| 400 | Bad Request |
| 401 | Unauthorized |
| 403 | Forbidden |
| 404 | Not Found |
| 500 | Server Error |
