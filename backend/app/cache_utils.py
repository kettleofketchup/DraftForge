"""
Cache invalidation utilities for cacheops + Django transactions.

All cache eviction in this codebase should go through this module's
wrappers — `invalidate_obj`, `invalidate_model`, and `invalidate_after_commit`
all emit structured `system="cache", subsystem="invalidate"` log entries
so eviction frequency is visible on the subsystem-logs Grafana dashboard.
Importing `invalidate_obj` directly from `cacheops` bypasses the telemetry.
"""

from cacheops import invalidate_model as _cacheops_invalidate_model
from cacheops import invalidate_obj as _cacheops_invalidate_obj
from django.db import transaction
from django.db.models import Model

from telemetry.logging import get_logger

log = get_logger(__name__)


def invalidate_obj(obj: Model) -> None:
    """Evict a single cached object and emit a `cache_invalidate` log.

    Drop-in replacement for `cacheops.invalidate_obj` — same signature,
    same effect, plus structured logging tagged
    `system=cache, subsystem=invalidate`.

    Use inside non-transactional code paths or outside `atomic()` blocks.
    Inside a transaction, prefer `invalidate_after_commit` so the eviction
    fires only after the write actually commits.
    """
    log.info(
        "cache_invalidate",
        system="cache",
        subsystem="invalidate",
        obj_class=obj.__class__.__name__,
        obj_pk=obj.pk,
    )
    _cacheops_invalidate_obj(obj)


def invalidate_model(model: type[Model]) -> None:
    """Evict every cached entry for a model and emit a `cache_invalidate_model` log.

    Logged at INFO — it's measurement data, not an error. Migrations
    legitimately use it for schema changes, and a few bulk paths
    legitimately need it. Spike detection happens via the dashboard's
    `cache_invalidate_model` panel rather than warn/error rate.

    For bulk_update of <1k rows, prefer looping `invalidate_obj` per
    row so unrelated cached entries for the same model survive.
    """
    log.info(
        "cache_invalidate_model",
        system="cache",
        subsystem="invalidate",
        obj_class=model.__name__,
    )
    _cacheops_invalidate_model(model)


def invalidate_after_commit(*objs: Model) -> None:
    """
    Schedule cacheops invalidation for the given model instances,
    deferred until the current database transaction commits.

    If called outside a transaction, the callback fires immediately.

    Usage::

        with transaction.atomic():
            user.nickname = "New"
            user.save()
            invalidate_after_commit(tournament, org_user, org_user.organization)
    """

    def _do():
        for obj in objs:
            invalidate_obj(obj)

    transaction.on_commit(_do)
