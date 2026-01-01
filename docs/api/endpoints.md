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
