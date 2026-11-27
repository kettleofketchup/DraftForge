from contextvars import ContextVar
from dataclasses import dataclass
from uuid import UUID

from org.models import OrgMmrSyncState, OrgUser

deferred_identity_members: ContextVar[set[int] | None] = ContextVar(
    "deferred_identity_members", default=None
)


@dataclass(frozen=True)
class MmrMutationContext:
    origin_connection_id: int | None = None
    run_id: UUID | None = None
    expected_revision: int | None = None


class MmrRevisionConflict(ValueError):
    code: str = "conflict"


def check_expected_revision(
    org_user: OrgUser, game_type: int, context: MmrMutationContext | None
) -> None:
    if context is None or context.expected_revision is None:
        return
    revision = (
        OrgMmrSyncState.objects.filter(org_user=org_user, game_type=game_type)
        .values_list("revision", flat=True)
        .first()
        or 0
    )
    if revision != context.expected_revision:
        raise MmrRevisionConflict("conflict")


def lock_memberships(ids: list[int], *, required: bool = True) -> list[OrgUser]:
    members = list(
        OrgUser.objects.nocache().select_for_update().filter(pk__in=ids).order_by("pk")
    )
    if required and len(members) != len(set(ids)):
        raise OrgUser.DoesNotExist
    return members
