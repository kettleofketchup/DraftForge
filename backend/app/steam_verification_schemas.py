"""Request and response bodies for /api/users/<pk>/steam-verification/.

Pydantic, no Django imports: `just py::gen-steam-verification` exports these
to frontend/app/features/steam-verification/api.generated.ts.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SteamVerificationOut(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    steam_account_id: int | None
    steam_account_verified: bool
    steam_account_verified_at: datetime | None
    steam_account_verified_org_name: str | None
    steam_account_exists_checked: bool
    steam_profile_url: str | None
    dotabuff_url: str | None
    can_verify: bool


class SteamVerificationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verified: bool
    steam_account_id: int = Field(ge=1)


class SteamVerificationApi(BaseModel):
    verification: SteamVerificationOut
    verification_update: SteamVerificationIn
