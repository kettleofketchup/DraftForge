---
applyTo: "backend/**/*.py"
---

# Django + Redis caching (django-cacheops)

Canonical: `.claude/skills/django-redis-caching/SKILL.md`. Verify what is/isn't cached against the `CACHEOPS` dict in `backend/app/settings.py` — that is the source of truth, not any summary table.

## Rules

- **Never call `cache.delete(...)` directly.** Cacheops invalidates on model `save()` for any model registered in `CACHEOPS`. Manual invalidation is a code smell and almost always wrong.
- **Inside a `transaction.atomic()` block (or any deferred-write context like signal handlers): use `invalidate_after_commit(...)` from `app.cache_utils`.** Direct `invalidate_obj` during a transaction invalidates before the write commits and re-populates the cache with stale data.
- **Outside transactions (e.g., right after a M2M `.add()` / `.remove()`): `invalidate_obj` is fine.** That's the only place it's the right call.
- **View-level caching uses `@cached_as(Model1, Model2, ..., extra=cache_key, timeout=...)`.** The `extra` must include `request.get_full_path()` (or equivalent discriminator) — otherwise different query strings collide on the same key.
- **Cache timeouts come from `settings.CACHEOPS`.** Don't hard-code timeouts on individual views unless there's a documented reason; let the model-level config govern.
- **New models that need caching must be added to `CACHEOPS`** in `settings.py`. A view that caches a queryset over an unregistered model will not invalidate on writes.
- **DRF list/retrieve methods overriding `.list()` / `.retrieve()` should follow the inner `@cached_as` helper pattern** shown in the skill — outer method assembles the request-scoped `cache_key`, inner function does the actual work and is the one decorated.

## Out of scope here

Logging, testing, migrations, and Celery/task-queue patterns are not covered by this file — see their own `.instructions.md` (if present) or the matching `.claude/skills/` skill.
