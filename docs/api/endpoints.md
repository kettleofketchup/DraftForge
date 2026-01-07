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

## Drafts

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/drafts/` | List drafts |
| GET | `/api/drafts/{id}/` | Get draft details |
| POST | `/api/tournaments/init-draft` | Initialize draft for tournament |
| POST | `/api/tournaments/pick_player` | Pick player for draft round |
| GET | `/api/active-draft-for-user/` | Get active draft turn for current user |

### Pick Player

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
