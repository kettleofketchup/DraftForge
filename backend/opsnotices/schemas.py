from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

PositiveId = Annotated[StrictInt, Field(gt=0)]


class EmitNoticeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: StrictStr
    payload: dict[str, Any]
    organization_id: PositiveId
    event_id: PositiveId | None = None
    event_name: StrictStr | None = None
    event_repeater_id: PositiveId | None = None
    subject_user_id: PositiveId | None = None
    actor_id: PositiveId | None = None
    dedupe_key: StrictStr | None = None
    severity: StrictStr | None = None
    emit_id: UUID | None = None


class ResolveNoticeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: StrictStr
    dedupe_key: Annotated[StrictStr, Field(min_length=1)]
    organization_id: PositiveId
    event_id: PositiveId | None = None
    reason: StrictStr
