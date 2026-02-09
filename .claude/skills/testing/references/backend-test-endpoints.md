# Backend Test Endpoints

Source: `backend/tests/urls.py` (routing), `backend/tests/test_auth.py` (implementations)

All endpoints live under `/api/tests/`. Only active when `TEST=true` in environment.

## Security Model

Every endpoint:
- `@csrf_exempt` + `@api_view(["POST"])` (or GET for reads)
- `@authentication_classes([])` + `@permission_classes([AllowAny])`
- Checks `isTestEnvironment(request)` first, returns 404 if not test mode

## Authentication Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/tests/login-admin/` | POST | Login as superuser (pk=1001) |
| `/api/tests/login-staff/` | POST | Login as staff (pk=1002) |
| `/api/tests/login-user/` | POST | Login as regular user (pk=1003) |
| `/api/tests/login-user-claimer/` | POST | Login as user_claimer (pk=1011) |
| `/api/tests/login-org-admin/` | POST | Login as org admin (pk=1020) |
| `/api/tests/login-org-staff/` | POST | Login as org staff (pk=1021) |
| `/api/tests/login-league-admin/` | POST | Login as league admin (pk=1030) |
| `/api/tests/login-league-staff/` | POST | Login as league staff (pk=1031) |
| `/api/tests/login-as/` | POST | Login as any user by `user_pk` body param |
| `/api/tests/login-as-discord/` | POST | Login as any user by `discord_id` body param |

### How Login Works

1. `createTestXXXUser()` checks if user with specific PK exists, creates if missing
2. `create_social_auth(user)` sets up Discord OAuth records
3. `login(request, user, backend="django.contrib.auth.backends.ModelBackend")` establishes session
4. `return_tokens(user)` extracts session/csrf/access tokens from `get_social_token()`

## Test Data Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/tests/tournament-by-key/<key>/` | GET | Look up tournament by string key |
| `/api/tests/user/<user_pk>/org-membership/` | GET | Get user's org membership info |
| `/api/tests/create-claimable-user/` | POST | Create a user with Steam but no Discord (claimable) |
| `/api/tests/create-claim-request/` | POST | Create a profile claim request |
| `/api/tests/create-match/` | POST | Create a test match record |

## HeroDraft Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/tests/herodraft/<draft_pk>/force-timeout/` | POST | Force timeout on current pick |
| `/api/tests/herodraft/<draft_pk>/reset/` | POST | Reset draft to initial state |
| `/api/tests/herodraft-by-key/<key>/` | GET | Look up herodraft by string key |

## Demo Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/tests/demo/bracket/<tournament_pk>/generate/` | POST | Generate demo bracket data |
| `/api/tests/demo/<key>/reset/` | POST | Reset demo tournament |
| `/api/tests/demo/<key>/` | GET | Get demo tournament info |

## URL Registration

Test URLs included conditionally in `backend/app/urls.py`:

```python
if settings.TEST:
    urlpatterns += [path("api/tests/", include("tests.urls"))]
```

## State Reset Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/tests/org/<org_pk>/reset-admin-team/` | POST | Reset org admin team to populate defaults |

State reset endpoints are critical for test isolation. They reset DB state AND invalidate cacheops cache.

### Cacheops Cache Invalidation in Reset Endpoints

**Django cacheops does NOT auto-invalidate when M2M relationships are modified** via `.add()`, `.remove()`, or `.clear()`. After modifying M2M fields in test reset endpoints, you MUST call `invalidate_obj()`:

```python
from cacheops import invalidate_obj

# After M2M changes:
org.admins.clear()
org.staff.clear()
org.admins.add(admin_user)
invalidate_obj(org)  # REQUIRED — otherwise GET returns stale cached data
```

Without this, subsequent API requests (e.g., `GET /organizations/1/`) will return cached data that doesn't reflect the M2M changes, causing test flakes.

**This also applies to production views** — see `backend/app/views/admin_team.py` for the pattern where every M2M mutation (`add_org_admin`, `remove_org_staff`, etc.) calls `invalidate_obj()` after the change.

## Adding New Test Endpoints

1. Add view function to `backend/tests/test_auth.py`
2. Apply decorators: `@csrf_exempt`, `@api_view`, `@authentication_classes([])`, `@permission_classes([AllowAny])`
3. Check `isTestEnvironment(request)` at top
4. **If modifying M2M fields**: call `invalidate_obj(model)` after changes (cacheops doesn't auto-invalidate M2M)
5. Add URL pattern to `backend/tests/urls.py`
6. Add corresponding Playwright fixture function in `frontend/tests/playwright/fixtures/`
