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
