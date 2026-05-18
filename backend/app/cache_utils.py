"""
Cache invalidation utilities for cacheops + Django transactions.

The `invalidate_after_commit` helper ensures cacheops sees committed state
by deferring `invalidate_obj` calls until after the current transaction commits.

Use this inside `transaction.atomic()` blocks instead of calling `invalidate_obj`
manually after the block.
"""

from cacheops import invalidate_obj
from django.db import transaction
from django.db.models import Model

from telemetry.logging import get_logger

log = get_logger(__name__)


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
            log.info(
                "cache_invalidate",
                system="cache",
                subsystem="invalidate",
                obj_class=obj.__class__.__name__,
                obj_pk=obj.pk,
            )
            invalidate_obj(obj)

    transaction.on_commit(_do)
