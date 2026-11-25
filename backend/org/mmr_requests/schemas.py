"""Response models for GET /api/users/<pk>/mmrs/.

Pydantic, no Django imports: `export_schema.py` loads it with `python -I` to
generate `frontend/app/features/mmr-requests/summary.generated.ts`.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class _Response(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class UserRef(_Response):
    pk: int
    username: str


class OrgRef(_Response):
    pk: int
    name: str
    logo: str | None


class LeagueRef(_Response):
    pk: int
    name: str


class PendingRequestRef(_Response):
    id: int
    requested_mmr: int
    created_at: datetime


class LastDecision(_Response):
    id: int
    status: Literal["approved", "rejected", "superseded"]
    decided_mmr: int | None
    rejection_reason: str
    reviewed_at: datetime | None


class GameMmrEntry(_Response):
    game_type: int
    mmr: int
    verified: bool
    verified_at: datetime | None
    verified_by: UserRef | None
    legacy_verified: bool
    pending_request: PendingRequestRef | None
    last_decision: LastDecision | None


class OrgMmrEntry(_Response):
    organization: OrgRef
    org_user_pk: int | None
    game_mmrs: list[GameMmrEntry]


class LeagueMmrEntry(_Response):
    league: LeagueRef
    organization_pk: int | None
    league_user_pk: int | None
    mmr: int
    verified: bool
    verified_at: datetime | None
    verified_by: UserRef | None
    pending_request: PendingRequestRef | None
    last_decision: LastDecision | None


class UserMmrSummary(_Response):
    user_pk: int
    orgs: list[OrgMmrEntry]
    leagues: list[LeagueMmrEntry]
