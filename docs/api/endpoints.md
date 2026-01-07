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

## Drafts

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/drafts/` | List drafts |
| GET | `/api/drafts/{id}/` | Get draft details |
| PUT | `/api/drafts/{id}/` | Update draft (e.g., change style) |
| POST | `/api/tournaments/init-draft` | Initialize draft for tournament |
| POST | `/api/tournaments/pick_player` | Pick player for draft round |
| GET | `/api/active-draft-for-user/` | Get active draft turn for current user |

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

### Active Draft for User

Returns the user's active draft turn if they are a captain with a pending pick:

```bash
GET /api/active-draft-for-user/
```

Response:
```json
{
  "has_active_turn": true,
  "tournament_pk": 1,
  "tournament_name": "Spring Championship",
  "draft_pk": 5,
  "draft_round_pk": 42,
  "pick_number": 3
}
```

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
