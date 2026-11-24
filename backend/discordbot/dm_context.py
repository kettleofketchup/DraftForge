from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from discordbot.models import DMKind


class _Context(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SignupReminderContext(_Context):
    discord_event_id: int | None = None
    repeater_id: int | None = None


class TournamentLinkContext(_Context):
    draft_id: int | None = None
    game_id: int | None = None
    activity: bool = False


class LobbyInfoContext(_Context):
    side: Literal["radiant", "dire"]


class SignupConfirmationContext(_Context):
    result: Literal["signed_up", "tentative", "declined", "screenshot_saved"]
    interaction_id: int | str


class LeadershipReviewContext(_Context):
    snapshot_id: int
    part: int
    parts: int
    trait_ids: list[int]


class EmptyContext(_Context):
    pass


class _BackfillContext(_Context):
    legacy_kind_unknown: bool


CONTEXT_MODELS: dict[DMKind, type[BaseModel]] = {
    DMKind.SIGNUP_REMINDER: SignupReminderContext,
    DMKind.TOURNAMENT_DRAFT_LINK: TournamentLinkContext,
    DMKind.TOURNAMENT_HERODRAFT_LINK: TournamentLinkContext,
    DMKind.LOBBY_INFO: LobbyInfoContext,
    DMKind.SIGNUP_CONFIRMATION: SignupConfirmationContext,
    DMKind.LEADERSHIP_REVIEW: LeadershipReviewContext,
    DMKind.TEST_NOTIFICATION: EmptyContext,
}


def validate_context(
    kind: DMKind, data: Mapping[str, object], *, backfill: bool = False
) -> dict[str, object]:
    payload = dict(data)
    if (
        backfill
        and DMKind(kind) == DMKind.TOURNAMENT_DRAFT_LINK
        and set(payload) == {"legacy_kind_unknown"}
    ):
        model: type[BaseModel] = _BackfillContext
    else:
        model = CONTEXT_MODELS[DMKind(kind)]
    try:
        return model.model_validate(payload).model_dump(exclude_unset=True)
    except ValidationError as exc:
        raise ValueError(f"invalid {kind} DM context: {exc}") from exc
