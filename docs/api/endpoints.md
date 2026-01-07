# API Endpoints

All API endpoints are prefixed with `/api/`.

## Authentication

Authentication is handled via Discord OAuth through django-social-auth.

### Test Endpoints

For E2E testing, the following endpoints are available:

| Endpoint | Description |
|----------|-------------|
| `/api/test/login/user/` | Login as regular user |
| `/api/test/login/staff/` | Login as staff user |
| `/api/test/login/admin/` | Login as admin user |

!!! warning "Test Only"
    These endpoints are only available in test/development environments.

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

## Drafts

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/drafts/` | List drafts |
| GET | `/api/drafts/{id}/` | Get draft details |
| PUT | `/api/drafts/{id}/` | Update draft (e.g., change style) |

### Draft Pick

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
