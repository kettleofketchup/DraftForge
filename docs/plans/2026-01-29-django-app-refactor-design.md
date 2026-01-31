# Django App Refactor Design

**Date:** 2026-01-29
**Status:** Approved
**Goal:** Split monolithic `backend/app/` into focused Django apps for better organization, team scalability, and reusability.

## Motivation

- `app/models.py` is 1,793 lines with ~25 models
- `app/serializers.py` is 964 lines
- `app/views_main.py` is 1,083 lines
- Hard to navigate, maintain, and work on concurrently

## Final App Structure

| App | Models | Dependencies |
|-----|--------|--------------|
| `users` | CustomUser, PositionsModel | None |
| `misc` | Joke | users |
| `orgs` | Organization, League, OrgLog, LeagueLog, LeagueRating, LeagueMatch, LeagueMatchParticipant | users |
| `tournaments` | Tournament, Team, Game | users, orgs |
| `drafts` | Draft, DraftRound, DraftEvent, HeroDraft, DraftTeam, HeroDraftRound, HeroDraftEvent | users, tournaments |
| `steam` | *(unchanged)* | users |

### Dependency Graph

```
users (base)
  ├── misc
  ├── orgs
  │     └── tournaments
  │           └── drafts
  └── steam (already exists)
```

### Directory Structure

```
backend/
├── users/
│   ├── models.py       # CustomUser, PositionsModel
│   ├── serializers.py
│   ├── views.py
│   ├── pipelines.py    # social auth
│   └── functions.py
├── misc/
│   ├── models.py       # Joke
│   ├── serializers.py
│   └── views.py
├── orgs/
│   ├── models.py       # Organization, League, *Log, LeagueRating, LeagueMatch, LeagueMatchParticipant
│   ├── serializers.py
│   ├── views.py
│   ├── views/
│   │   └── admin_team.py
│   ├── permissions.py  # from permissions_org.py
│   └── services/
│       ├── rating.py
│       └── match_finalization.py
├── tournaments/
│   ├── models.py       # Tournament, Team, Game
│   ├── serializers.py
│   ├── views.py
│   ├── views/
│   │   └── bracket.py
│   └── functions.py
├── drafts/
│   ├── models.py       # Draft*, HeroDraft*
│   ├── serializers.py
│   ├── views.py
│   ├── views/
│   │   └── herodraft.py
│   ├── consumers.py
│   ├── broadcast.py
│   ├── routing.py
│   └── functions/
│       ├── shuffle_draft.py
│       └── herodraft.py
├── steam/              # unchanged
└── app/                # deleted after migration
```

## Design Decisions

### Cross-App Foreign Keys
Use direct string references:
```python
# In tournaments/models.py
class Tournament(models.Model):
    league = models.ForeignKey("orgs.League", ...)
```

### Table Naming
Rename tables to match new app names (clean approach):
- `app_customuser` → `users_customuser`
- `app_tournament` → `tournaments_tournament`
- etc.

### Migration Strategy
Incremental by app, one PR per app in dependency order.

## Migration Process Per App

Using `users` as example:

### Step 1: Create app skeleton
```bash
cd backend
python manage.py startapp users
```

### Step 2: Move models
- Copy models from `app/models.py` to `users/models.py`
- Update imports to use string references for cross-app FKs
- Add `db_table = 'app_customuser'` temporarily

### Step 3: Create migration to rename table
```python
# users/migrations/0002_rename_tables.py
from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [('users', '0001_initial')]

    operations = [
        migrations.AlterModelTable(
            name='customuser',
            table='users_customuser',
        ),
        migrations.AlterModelTable(
            name='positionsmodel',
            table='users_positionsmodel',
        ),
    ]
```

### Step 4: Update all references
- Change imports throughout codebase
- Update serializers, views, admin, tests
- Update `AUTH_USER_MODEL` in settings (for users app)

### Step 5: Move related code
- Serializers → `users/serializers.py`
- Views → `users/views.py`
- Functions → `users/` directory

### Step 6: Update `app/models.py`
- Remove moved models
- Add backwards-compat import (temporary)

### Step 7: Test & commit
- Run migrations
- Run full test suite
- Commit as single PR

## What Moves Where

### App 1: `users`

| From | To |
|------|-----|
| `app/models.py` → CustomUser, PositionsModel | `users/models.py` |
| `app/serializers.py` → UserSerializer, PositionsSerializer | `users/serializers.py` |
| `app/views_main.py` → user-related views | `users/views.py` |
| `app/pipelines.py` | `users/pipelines.py` |
| `app/functions/user.py` | `users/functions.py` |

Settings: `AUTH_USER_MODEL = 'users.CustomUser'`

### App 2: `misc`

| From | To |
|------|-----|
| `app/models.py` → Joke | `misc/models.py` |
| `app/serializers.py` → JokeSerializer | `misc/serializers.py` |
| `app/views_joke.py` | `misc/views.py` |

### App 3: `orgs`

| From | To |
|------|-----|
| `app/models.py` → Organization, League, OrgLog, LeagueLog, LeagueRating, LeagueMatch, LeagueMatchParticipant | `orgs/models.py` |
| `app/serializers.py` → related serializers | `orgs/serializers.py` |
| `app/views_main.py` → org/league views | `orgs/views.py` |
| `app/views/admin_team.py` | `orgs/views/admin_team.py` |
| `app/permissions_org.py` | `orgs/permissions.py` |
| `app/services/rating.py` | `orgs/services/rating.py` |
| `app/services/match_finalization.py` | `orgs/services/match_finalization.py` |

### App 4: `tournaments`

| From | To |
|------|-----|
| `app/models.py` → Tournament, Team, Game | `tournaments/models.py` |
| `app/serializers.py` → related serializers | `tournaments/serializers.py` |
| `app/views_main.py` → tournament views | `tournaments/views.py` |
| `app/views/bracket.py` | `tournaments/views/bracket.py` |
| `app/functions/tournament.py` | `tournaments/functions.py` |

### App 5: `drafts`

| From | To |
|------|-----|
| `app/models.py` → Draft, DraftRound, DraftEvent, HeroDraft, DraftTeam, HeroDraftRound, HeroDraftEvent, HeroDraftState | `drafts/models.py` |
| `app/serializers.py` → related serializers | `drafts/serializers.py` |
| `app/views_main.py` → draft views | `drafts/views.py` |
| `app/functions/shuffle_draft.py` | `drafts/functions/shuffle_draft.py` |
| `app/functions/herodraft.py` | `drafts/functions/herodraft.py` |
| `app/functions/herodraft_views.py` | `drafts/views/herodraft.py` |
| `app/consumers.py` | `drafts/consumers.py` |
| `app/broadcast.py` | `drafts/broadcast.py` |
| `app/routing.py` | `drafts/routing.py` |

## Gotchas & Considerations

### AUTH_USER_MODEL change
- Django doesn't support changing `AUTH_USER_MODEL` easily on existing projects
- Keep actual database table as `app_customuser` initially
- Use raw SQL migration to rename
- Update all `ForeignKey(User, ...)` to `ForeignKey(settings.AUTH_USER_MODEL, ...)`

### Circular import prevention
- Use string references for all cross-app FKs: `ForeignKey("users.CustomUser", ...)`
- Use lazy imports inside functions when needed

### Migration dependencies
Each app's migrations must declare dependencies:
```python
# orgs/migrations/0001_initial.py
dependencies = [
    ('users', '0001_initial'),
]
```

### Cacheops invalidation
- Update `invalidate_model(CustomUser)` imports throughout
- Or use string-based invalidation

### URL routing
Split `app/urls.py` to include new app URLs:
```python
urlpatterns = [
    path('', include('users.urls')),
    path('', include('orgs.urls')),
    path('', include('tournaments.urls')),
    path('', include('drafts.urls')),
    path('', include('misc.urls')),
]
```

### WebSocket routing
- Move `app/routing.py` to `drafts/routing.py`
- Update imports in ASGI config

### Tests
- Update all `from app.models import` to appropriate new apps
- Can do search/replace per PR

## Implementation Checklist

### Phase 1: `users` app
- [ ] Create `users/` app skeleton
- [ ] Move CustomUser, PositionsModel to `users/models.py`
- [ ] Update `AUTH_USER_MODEL` setting
- [ ] Move user serializers, views, pipelines
- [ ] Update all `from app.models import CustomUser` imports
- [ ] Create table rename migration
- [ ] Run tests, fix breakages
- [ ] PR & merge

### Phase 2: `misc` app
- [ ] Create `misc/` app skeleton
- [ ] Move Joke model
- [ ] Move views_joke.py content
- [ ] Update imports, create migration
- [ ] PR & merge

### Phase 3: `orgs` app
- [ ] Create `orgs/` app skeleton
- [ ] Move Organization, League, and rating models
- [ ] Move services/rating.py, services/match_finalization.py
- [ ] Move permissions_org.py → orgs/permissions.py
- [ ] Move views/admin_team.py
- [ ] Update imports, create migrations
- [ ] PR & merge

### Phase 4: `tournaments` app
- [ ] Create `tournaments/` app skeleton
- [ ] Move Tournament, Team, Game
- [ ] Move views/bracket.py, functions/tournament.py
- [ ] Update imports, create migrations
- [ ] PR & merge

### Phase 5: `drafts` app
- [ ] Create `drafts/` app skeleton
- [ ] Move all Draft* and HeroDraft* models
- [ ] Move consumers.py, broadcast.py, routing.py
- [ ] Move shuffle_draft.py, herodraft.py, herodraft_views.py
- [ ] Update imports, create migrations
- [ ] PR & merge

### Phase 6: Cleanup
- [ ] Delete empty `app/` directory
- [ ] Remove backwards-compat imports
- [ ] Final test sweep
- [ ] Update documentation
