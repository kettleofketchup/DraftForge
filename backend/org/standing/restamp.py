import contextlib
from collections.abc import Callable, Iterable, Iterator, Sequence

from django.db import transaction

from org.models import OrgUser

OrgRestamp = Callable[[int], int]
MemberRestamp = Callable[[Sequence[OrgUser]], int]

_org_fn: OrgRestamp | None = None
_member_fn: MemberRestamp | None = None


def register(org_fn: OrgRestamp, member_fn: MemberRestamp) -> None:
    global _org_fn, _member_fn
    _org_fn, _member_fn = org_fn, member_fn


def registered() -> bool:
    return _org_fn is not None and _member_fn is not None


@contextlib.contextmanager
def override(
    org_fn: OrgRestamp | None, member_fn: MemberRestamp | None
) -> Iterator[None]:
    global _org_fn, _member_fn
    saved = (_org_fn, _member_fn)
    _org_fn, _member_fn = org_fn, member_fn
    try:
        yield
    finally:
        _org_fn, _member_fn = saved


def _unregistered() -> RuntimeError:
    return RuntimeError("eligibility re-stamp is not registered")


def org_on_commit(org_id: int) -> None:
    fn = _org_fn
    if fn is None:
        raise _unregistered()
    transaction.on_commit(lambda: fn(org_id))


def member_on_commit(org_users: Iterable[OrgUser]) -> None:
    fn = _member_fn
    if fn is None:
        raise _unregistered()
    targets = tuple({org_user.pk: org_user for org_user in org_users}.values())
    if targets:
        transaction.on_commit(lambda: fn(targets))
