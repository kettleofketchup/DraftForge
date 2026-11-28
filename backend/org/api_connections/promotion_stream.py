"""Which connection holds an org's single promotion stream."""

from collections.abc import Iterable

from org.api_tokens.operations import PROMOTION_OPERATIONS
from org.models import Organization, OrgApiConnection, OrgApiPromotionAdoption


class PromotionStreamError(Exception):
    def __init__(self, code: str, status: int = 409) -> None:
        self.code = code
        self.status = status
        super().__init__(code)


def lock_org(org_id: int) -> Organization:
    return Organization.objects.nocache().select_for_update().get(pk=org_id)


def holds_promotion_grants(operations: Iterable[str]) -> bool:
    return not PROMOTION_OPERATIONS.isdisjoint(operations)


def promotion_stream_holder(org_id: int) -> int | None:
    """The one connection allowed promotion grants: adopted, else legacy holder."""
    adopted = (
        OrgApiPromotionAdoption.objects.filter(organization_id=org_id)
        .values_list("connection_id", flat=True)
        .first()
    )
    if adopted is not None:
        return adopted
    candidates = (
        OrgApiConnection.objects.filter(
            organization_id=org_id, archived_at__isnull=True
        )
        .order_by("-legacy_multi_credential", "pk")
        .values_list("pk", "operations")
    )
    return next(
        (pk for pk, operations in candidates if holds_promotion_grants(operations)),
        None,
    )
