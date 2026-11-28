"""Operations an org app token can be granted, and the feature each needs.

A token only reaches a route whose operation it was granted. Tokens issued
without naming operations, and every token that predates grants, hold the
MMR pair and nothing else; promotion grants must be asked for explicitly by
an org admin.

This module must not import models: ``OrgApiToken.operations`` uses
``default_operations`` as its field default.
"""

from collections.abc import Iterable
from enum import StrEnum
from typing import Any

from org.feature_keys import FeatureKey


class Operation(StrEnum):
    MMR_READ = "mmr:read"
    MMR_WRITE = "mmr:write"
    PROMOTION_IMPORT = "promotion:import"
    PROMOTION_READ = "promotion:read"
    PROMOTION_WRITE = "promotion:write"


PROMOTION_OPERATIONS: frozenset[str] = frozenset(
    {
        Operation.PROMOTION_IMPORT.value,
        Operation.PROMOTION_READ.value,
        Operation.PROMOTION_WRITE.value,
    }
)

_ENTITLEMENTS: dict[Operation, FeatureKey] = {
    Operation.MMR_READ: FeatureKey.MMR_SYNC,
    Operation.MMR_WRITE: FeatureKey.MMR_SYNC,
    Operation.PROMOTION_IMPORT: FeatureKey.PROMOTION,
    Operation.PROMOTION_READ: FeatureKey.PROMOTION,
    Operation.PROMOTION_WRITE: FeatureKey.PROMOTION,
}


def default_operations() -> list[str]:
    """Grants for a token whose issuer named none: the MMR pair only."""
    return [Operation.MMR_READ.value, Operation.MMR_WRITE.value]


def entitlement_for(operation: Operation | str) -> FeatureKey:
    return _ENTITLEMENTS[Operation(operation)]


def entitlements_for(operations: Iterable[str]) -> list[FeatureKey]:
    return sorted({entitlement_for(op) for op in operations})


def parse_operations(raw: Any) -> list[str]:
    """Validate requested grants: a nonempty list of known operation strings.

    Returns them deduplicated and sorted, which is how they are stored.
    """
    if not isinstance(raw, list) or not raw:
        raise ValueError("operations must be a nonempty list")
    known = {op.value for op in Operation}
    if not all(isinstance(op, str) and op in known for op in raw):
        raise ValueError("unknown operation")
    return sorted(set(raw))
