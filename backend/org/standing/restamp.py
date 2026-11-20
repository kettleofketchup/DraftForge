from collections.abc import Callable, Iterable

from django.db import transaction

from org.models import OrgUser

OrgRestamp = Callable[[int], int]
MembersRestamp = Callable[[Iterable[OrgUser]], int]

_slot: dict[str, Callable[..., int]] = {}


def register(org_fn: OrgRestamp, members_fn: MembersRestamp) -> None:
    _slot["org"] = org_fn
    _slot["members"] = members_fn


def _get(name: str) -> Callable[..., int]:
    fn = _slot.get(name)
    if fn is None:
        raise RuntimeError("eligibility re-stamp slot is not registered")
    return fn


def org_on_commit(org_id: int) -> None:
    fn = _get("org")
    transaction.on_commit(lambda: fn(org_id))


def members_on_commit(org_users: Iterable[OrgUser]) -> None:
    targets = list({org_user.pk: org_user for org_user in org_users}.values())
    if not targets:
        return
    fn = _get("members")
    transaction.on_commit(lambda: fn(targets))
