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
  "seasons": [{ "id": 1, "name": "Season 1", "status": "active" }],
  "tournament_count": 4,
  "season_count": 1
}
```

## Seasons

Seasons organize tournaments within a league. A season contains a player pool (via signups), teams, and links to tournaments.

!!! info "Planned Feature"
    Seasons are a planned feature. See [Team Management & Seasons](../features/planned/team-management.md) for the full design.

### Season CRUD

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/leagues/{id}/seasons/` | List seasons for a league | No |
| POST | `/api/leagues/{id}/seasons/` | Create a season | League Admin |
| GET | `/api/leagues/{id}/seasons/{season_id}/` | Get season details | No |
| PUT | `/api/leagues/{id}/seasons/{season_id}/` | Update season | League Admin |
| PATCH | `/api/leagues/{id}/seasons/{season_id}/` | Partial update season | League Admin |
| DELETE | `/api/leagues/{id}/seasons/{season_id}/` | Delete season | League Admin |

**Request Body (create/update):**

```json
{
  "name": "Season 3",
  "number": 3,
  "status": "upcoming",
  "start_date": "2026-03-01T00:00:00Z",
  "end_date": "2026-06-01T00:00:00Z",
  "signup_deadline": "2026-02-28T23:59:59Z",
  "timezone": "America/New_York"
}
```

**Response (detail):**

```json
{
  "id": 1,
  "league": 1,
  "name": "Season 3",
  "number": 3,
  "status": "active",
  "start_date": "2026-03-01T00:00:00Z",
  "end_date": "2026-06-01T00:00:00Z",
  "signup_deadline": "2026-02-28T23:59:59Z",
  "timezone": "America/New_York",
  "member_count": 24,
  "team_count": 4,
  "tournament_count": 3,
  "created_at": "2026-02-01T00:00:00Z",
  "updated_at": "2026-02-15T00:00:00Z"
}
```

### Season Signups

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/seasons/{id}/signups/` | List all signups | League Staff |
| GET | `/api/seasons/{id}/signups/me/` | Get current user's signup | LeagueUser |
| POST | `/api/seasons/{id}/signups/` | Sign up for season | LeagueUser |
| DELETE | `/api/seasons/{id}/signups/{signup_id}/` | Withdraw signup | Owner |
| POST | `/api/seasons/{id}/signups/{signup_id}/accept/` | Accept signup | League Admin |
| POST | `/api/seasons/{id}/signups/{signup_id}/reject/` | Reject signup | League Admin |
| POST | `/api/seasons/{id}/signups/bulk-accept/` | Accept multiple signups | League Admin |

**Request Body (sign up):**

```json
{
  "note": "Prefer to play support"
}
```

**Request Body (bulk accept):**

```json
{
  "signup_ids": [1, 2, 3, 5]
}
```

**Response (signup detail):**

```json
{
  "id": 1,
  "season": 1,
  "league_user": {
    "id": 5,
    "user": { "id": 10, "username": "player1", "avatar": "https://..." },
    "mmr": 4500
  },
  "status": "pending",
  "note": "Prefer to play support",
  "signed_up_at": "2026-02-10T14:30:00Z",
  "reviewed_by": null,
  "reviewed_at": null
}
```

### Season Members

Members are derived from accepted signups. These endpoints provide convenience access.

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/seasons/{id}/members/` | List accepted members | No |
| POST | `/api/seasons/{id}/members/` | Add member directly (auto-accepts signup) | League Admin |
| DELETE | `/api/seasons/{id}/members/{league_user_id}/` | Remove member | League Admin |

**Request Body (direct add):**

```json
{
  "league_user_id": 5
}
```

**Response (member list item):**

```json
{
  "id": 5,
  "user": { "id": 10, "username": "player1", "avatar": "https://..." },
  "mmr": 4500,
  "signed_up_at": "2026-02-10T14:30:00Z"
}
```

### Season Teams

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/seasons/{id}/teams/` | List season teams | No |
| POST | `/api/seasons/{id}/teams/` | Create team | League Admin |
| GET | `/api/seasons/{id}/teams/{team_id}/` | Get team details | No |
| PUT | `/api/seasons/{id}/teams/{team_id}/` | Update team | League Admin |
| PATCH | `/api/seasons/{id}/teams/{team_id}/` | Partial update | League Admin |
| DELETE | `/api/seasons/{id}/teams/{team_id}/` | Delete team | League Admin |
| POST | `/api/seasons/{id}/teams/{team_id}/logo/` | Upload team logo | League Admin |

**Request Body (create/update):**

```json
{
  "name": "Team Phoenix",
  "captain_id": 5,
  "deputy_captain_id": 8,
  "member_ids": [5, 8, 12, 15, 20]
}
```

**Request Body (logo upload):**

Multipart form data with `logo` file field.

**Response (team detail):**

```json
{
  "id": 1,
  "season": 1,
  "name": "Team Phoenix",
  "captain": {
    "id": 5,
    "user": { "id": 10, "username": "captain1", "avatar": "https://..." },
    "mmr": 5000
  },
  "deputy_captain": {
    "id": 8,
    "user": { "id": 14, "username": "deputy1", "avatar": "https://..." },
    "mmr": 4200
  },
  "members": [
    { "id": 5, "user": { "id": 10, "username": "captain1" }, "mmr": 5000 },
    { "id": 8, "user": { "id": 14, "username": "deputy1" }, "mmr": 4200 },
    { "id": 12, "user": { "id": 18, "username": "player2" }, "mmr": 3800 },
    { "id": 15, "user": { "id": 21, "username": "player3" }, "mmr": 3500 },
    { "id": 20, "user": { "id": 26, "username": "player4" }, "mmr": 3200 }
  ],
  "logo": "/media/season_teams/team-phoenix.png",
  "created_at": "2026-02-15T00:00:00Z",
  "updated_at": "2026-02-15T00:00:00Z"
}
```

### Tournament Team Import

Import SeasonTeams into a tournament as Tournament Teams.

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/api/tournaments/{id}/import-season-teams/` | Import teams from season | Tournament Staff |

**Request Body:**

```json
{
  "season_team_ids": [1, 2, 3, 4]
}
```

Omit `season_team_ids` to import all teams from the tournament's linked season.

**Response:**

```json
{
  "imported": 4,
  "teams": [
    { "id": 50, "name": "Team Phoenix", "season_team_source": 1 },
    { "id": 51, "name": "Team Dragon", "season_team_source": 2 },
    { "id": 52, "name": "Team Hydra", "season_team_source": 3 },
    { "id": 53, "name": "Team Kraken", "season_team_source": 4 }
  ]
}
```

!!! note "Import Behavior"
    - Tournament must have a linked season (`tournament.season` is set)
    - Import creates independent copies — changes to SeasonTeams after import do not propagate
    - Re-importing when teams already exist will error unless existing teams are removed first
    - LeagueUser references are resolved to CustomUser for Tournament Team compatibility

## CSV Import

Bulk-import users into organizations or tournaments via pre-parsed CSV data.

!!! info "Feature Documentation"
    See [CSV Import](../features/csv-import.md) for the full design.

### Organization CSV Import

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/api/organizations/{id}/import-csv/` | Bulk-import users to org | Org Staff |

**Request Body:**

```json
{
  "rows": [
    {
      "steam_friend_id": "76561198012345678",
      "discord_id": "123456789012345678",
      "base_mmr": 5000
    }
  ]
}
```

**Response:**

```json
{
  "summary": {
    "added": 2,
    "skipped": 1,
    "created": 1,
    "errors": 0
  },
  "results": [
    {
      "row": 1,
      "status": "added",
      "user": { "pk": 10, "username": "player1", "avatar": "..." },
      "created": false
    },
    {
      "row": 2,
      "status": "added",
      "user": { "pk": 50, "username": "steam_76561198099999999" },
      "created": true,
      "warning": "Steam ID already linked to different Discord ID — provided Discord ID was ignored"
    },
    {
      "row": 3,
      "status": "skipped",
      "reason": "Already a member",
      "user": { "pk": 5, "username": "existing_member" }
    }
  ]
}
```

| Summary Field | Description |
|---------------|-------------|
| `added` | Users successfully added to the organization |
| `skipped` | Users already in the organization |
| `created` | New stub users created (subset of `added`) |
| `errors` | Rows that failed to process |

### Tournament CSV Import

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/api/tournaments/{id}/import-csv/` | Bulk-import users to tournament | Org Staff |

Same request/response format as organization import. Additional per-row fields:

| Field | Type | Description |
|-------|------|-------------|
| `team_name` | string | Optional team assignment (request) |
| `team` | string | Team name assigned (response) |

!!! note "Tournament Import Behavior"
    - Creates OrgUser in parent organization if user is not already a member
    - Adds user to `tournament.users` M2M
    - Creates Team by name if `team_name` provided and team doesn't exist
    - Groups rows with same `team_name` into the same team
    - Maximum 500 rows per import

### CSV Import Error Responses

| Status | Condition |
|--------|-----------|
| 400 | `rows` is not a list, or exceeds 500 row limit |
| 403 | User lacks org staff access |
| 404 | Organization or tournament not found |

## Auction House

Real-time auction-based team formation with salary cap budgets and nomination rotation.

!!! info "Planned Feature"
    Auction House is a planned feature. See [Auction House](../features/planned/auction-house.md) for the full design.

### Auction CRUD

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/api/tournaments/{id}/create-auction/` | Create auction for tournament | Org Staff |
| POST | `/api/seasons/{id}/create-auction/` | Create auction for season | League Admin |
| GET | `/api/auctions/{id}/` | Get auction state (teams, budgets, lots, current phase) | No |
| POST | `/api/auctions/{id}/pause/` | Admin pause auction | Org Staff |
| POST | `/api/auctions/{id}/resume/` | Admin resume auction | Org Staff |
| POST | `/api/auctions/{id}/abort/` | Abort auction | Org Staff |
| GET | `/api/auctions/{id}/results/` | Final results and spending breakdown | No |

**Response (auction state):**

```json
{
  "id": 1,
  "status": "bidding",
  "tournament": 5,
  "season": null,
  "config": { "budget": 2000, "min_bid": 5, "bid_timer": 20, "..." : "..." },
  "teams": [
    { "team_id": 1, "name": "Team Phoenix", "budget_remaining": 1200, "players_won": 2, "pause_count": 0 }
  ],
  "current_lot": {
    "lot_number": 5,
    "player": { "pk": 10, "username": "mid_player" },
    "nominator": "Team Dragon",
    "highest_bid": 350,
    "highest_bidder": "Team Phoenix",
    "time_remaining": 8
  },
  "remaining_pool_count": 12
}
```

**Response (results):**

```json
{
  "auction_id": 1,
  "status": "completed",
  "teams": [
    {
      "team_id": 1,
      "team_name": "Team Phoenix",
      "budget_start": 2000,
      "budget_spent": 1847,
      "players": [
        { "user": { "pk": 10, "username": "star_player" }, "cost": 800, "lot_number": 3 },
        { "user": { "pk": 30, "username": "pos4" }, "cost": 0, "lot_number": null, "fallback": true }
      ]
    }
  ],
  "lots": [
    { "lot_number": 1, "player": { "pk": 5, "username": "mid_player" }, "winning_team": "Team Dragon", "winning_bid": 650, "bid_count": 8 }
  ]
}
```

### AuctionConfig (Cascading)

Configuration inherits down: Organization → League → Season → Tournament. Null fields inherit from parent.

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/organizations/{id}/auction-config/` | Get org-level config | No |
| PUT | `/api/organizations/{id}/auction-config/` | Set org-level config | Org Admin |
| GET | `/api/leagues/{id}/auction-config/` | Get league-level config | No |
| PUT | `/api/leagues/{id}/auction-config/` | Set league-level config | League Admin |
| GET | `/api/seasons/{id}/auction-config/` | Get season-level config | No |
| PUT | `/api/seasons/{id}/auction-config/` | Set season-level config | League Admin |
| GET | `/api/tournaments/{id}/auction-config/` | Get tournament-level config | No |
| PUT | `/api/tournaments/{id}/auction-config/` | Set tournament-level config | Org Staff |
| GET | `/api/tournaments/{id}/auction-config/resolved/` | Get fully merged config | No |

**Request/Response:**

```json
{
  "budget": 2000,
  "min_bid": 5,
  "bid_timer": null,
  "bid_extension_timer": null,
  "nomination_timer": null,
  "unsold_behavior": null,
  "max_roster_size": null,
  "fallback_mode": null,
  "max_pauses_per_captain": null,
  "reconnect_timeout": null
}
```

### Auction WebSocket

**Endpoint:** `/api/auction/{auction_id}/`

Real-time bidding via Daphne WebSocket (same pattern as HeroDraft).

**Client Messages:**

| Message | Payload | Description |
|---------|---------|-------------|
| `start` | — | Admin triggers auction start |
| `nominate` | `{ player_id: int }` | Captain nominates a player |
| `bid` | `{ amount: int }` | Place bid on current lot |

**Server Events:**

| Event | Description |
|-------|-------------|
| `auction_started` | Auction state, budgets, pool |
| `nomination_turn` | Captain ID, timer |
| `nomination` | Lot details, player, opening bid |
| `bid_placed` | Team, amount, time remaining |
| `lot_sold` | Winner, price, updated budgets |
| `lot_unsold` | Auto-assigned to nominator at min_bid |
| `fallback_pick` | Team, player, team MMR |
| `captain_disconnected` / `captain_reconnected` | Team ID, pause count |
| `auction_paused` / `auction_resumed` | Timestamp, reason |
| `auction_completed` | Final results |

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
