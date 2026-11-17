from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from opsnotices.services import RETENTION_MIN, purge_notices


@dataclass(frozen=True, slots=True)
class RetainedModel:
    model_label: str
    purge: Callable[..., int]
    timestamp_fields: tuple[str, ...]
    open_rows_kept: str
    minimum: timedelta


RETENTION: RetainedModel = RetainedModel(
    model_label="opsnotices.OpsNotice",
    purge=purge_notices,
    timestamp_fields=("closed_at", "last_seen_at"),
    open_rows_kept="urgent/task",
    minimum=RETENTION_MIN,
)
