---
name: django-redis-caching
description: Django Redis caching with django-cacheops. This skill should be used when implementing caching, adding cache invalidation, optimizing API performance, modifying models that affect cached data, or debugging cache-related issues in the Django backend.
---

# Django Redis Caching Skill

Implements Redis caching with django-cacheops for the DTX Django backend.

## Quick Reference

### Cacheops Configuration

All models use 1-hour cache timeout (configured in `settings.py`):
```python
CACHEOPS = {
    "app.tournament": {"ops": "all", "timeout": 60 * 60},
    "app.team": {"ops": "all", "timeout": 60 * 60},
    "app.customuser": {"ops": "all", "timeout": 60 * 60},
    "app.draft": {"ops": "all", "timeout": 60 * 60},
    "app.game": {"ops": "all", "timeout": 60 * 60},
    "app.draftround": {"ops": "all", "timeout": 60 * 60},
}
```

### View Caching Pattern

```python
from cacheops import cached_as

def list(self, request, *args, **kwargs):
    cache_key = f"model_list:{request.get_full_path()}"

    @cached_as(Model1, Model2, extra=cache_key, timeout=60 * 60)
    def get_data():
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return serializer.data

    return Response(get_data())
```

### Cache Invalidation Pattern

**Preferred: `invalidate_after_commit`** — use inside transactions, signal handlers, or anywhere writes may be deferred:

```python
from app.cache_utils import invalidate_after_commit

with transaction.atomic():
    user.nickname = "New"
    user.save()
    invalidate_after_commit(tournament, org_user, org_user.organization)
```

**Direct `invalidate_obj`** — safe only OUTSIDE transactions (e.g., after M2M `.add()`/`.remove()`):

```python
from cacheops import invalidate_obj

org.admins.add(user)       # M2M auto-commits
invalidate_obj(org)        # Safe — data already committed
```

**When to use which:**

| Context | Use |
|---------|-----|
| Inside `transaction.atomic()` | `invalidate_after_commit()` |
| Inside `@transaction.atomic` decorator | `invalidate_after_commit()` |
| Inside signal handlers (`post_save`, etc.) | `invalidate_after_commit()` |
| After `.save()` / M2M ops outside transactions | Direct `invalidate_obj()` is safe |
| After `.update()` / `.bulk_create()` | `invalidate_after_commit()` (defensive) |

## DTX Model Cache Dependencies

When modifying data, invalidate these related caches:

| Changed Model | Also Invalidate |
|---------------|-----------------|
| DraftRound | Tournament, Draft, Team |
| Draft | Tournament |
| Team | Tournament (if tournament-scoped) |
| Game | Tournament, Team |
| CustomUser | Team (if member changes) |

## Key Principles

1. **Invalidate on Write**: Always invalidate related caches after mutations
2. **Use `invalidate_after_commit`**: Default to deferred invalidation in transactions — see `app/cache_utils.py`
3. **Monitor Dependencies**: Use `@cached_as(Model1, Model2, ...)` to auto-invalidate
4. **Use Specific Keys**: Include request path or pk in cache keys
5. **Keep Fresh for Detail**: Use `keep_fresh=True` for single-object retrieval

## Detailed References

- [Cacheops Patterns](references/cacheops-patterns.md) - Decorator usage, cache keys
- [Invalidation Strategies](references/invalidation-strategies.md) - When and how to invalidate
- [Model Dependencies](references/model-dependencies.md) - DTX model relationships

## Common Operations

### Disable Cache for Management Commands

```python
DISABLE_CACHE=true python manage.py <command>
```

### Manual Cache Invalidation

```python
from cacheops import invalidate_all, invalidate_model, invalidate_obj

# Nuclear option - invalidate everything
invalidate_all()

# Invalidate all instances of a model
invalidate_model(Tournament)

# Invalidate specific instance
invalidate_obj(tournament)
```

### Check if Cache is Working

```python
from django.core.cache import cache
cache.set('test_key', 'test_value', 30)
print(cache.get('test_key'))  # Should print 'test_value'
```

## Timeout Guidelines

| Data Type | Timeout | Reason |
|-----------|---------|--------|
| Static data | 60 * 60 (1h) | Rarely changes |
| Tournament state | 60 * 10 (10m) | Changes during events |
| Draft rounds | 60 * 10 (10m) | Active during drafts |
| Discord guild members (`discord_members_<guild_id>`) | 60 * 60 (1h) | Admin-search-driven refreshes; daily avatar task reads from this same cache. See "Discord Member Cache" below. |
| Other external API short-burst caches | 15-60s | Per-request burst dedup only |

## Discord Member Cache

Single Redis cache for guild members shared by two consumer patterns —
admin-driven and scheduled. **Don't add a parallel cache for the same
data; extend the timeout or call `refresh_discord_members` instead.**

**Cache:** `discord_members_<guild_id>` — full paginated member list
per guild, 1-hour TTL (constant: `DISCORD_MEMBER_CACHE_TTL_S` in
`backend/discordbot/services/users.py`).

**Populated by:**
- `discordbot.services.users.get_discord_members_data(guild_id)` —
  on cache miss, paginates `GET /guilds/{id}/members?limit=1000` via
  the `after` cursor until the guild is exhausted, then writes the
  full list back at TTL.
- `discordbot.services.users.refresh_discord_members(request)` —
  POST endpoint admins hit when they need to add a user who joined
  Discord recently. 5-min per-org cooldown. Force-clears + repaves
  the cache.

**Consumed by:**
- `search_discord_members` — admin-search-by-name on org pages
- `get_organization_discord_members` — full org-member list
- `get_discord_voice_channel_activity` — voice-channel staffing
- `app.tasks.avatar_refresh.refresh_avatars_batched` — daily Celery
  beat. Reads the cache, builds a `discord_id → avatar_hash` map,
  bulk-updates `User.avatar`. Daily cadence works because admin
  searches keep the cache current within the day.

**Why no separate avatar cache?** Avatars are stored on `User.avatar`
(DB column), not in Redis. The "avatar cache" IS the DB column; the
daily Celery task is what refreshes it from the live guild member
list. No third cache needed.

**When you'd add a NEW cache key for guild members:** never. Use
`get_discord_members_data`. If a caller needs different semantics
(e.g. force-refresh), use the `refresh_discord_members` endpoint or
`cache.delete(...)` the existing key — don't fork.

### Bulk-update + cacheops invariant

When a Celery task writes thousands of rows via
`Model.objects.bulk_update(...)`, `post_save` doesn't fire and
cacheops won't auto-invalidate. Pair `bulk_update` with one
`invalidate_model(Model)` call after the batched write — N
per-row `invalidate_obj()` calls would defeat the whole point of
batching. The avatar refresh task uses this pattern; mirror it for
similar batched-write paths.
