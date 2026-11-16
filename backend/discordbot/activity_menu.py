"""Activity menu helpers: draft statuses, labels, notices and each user's first view."""

from dataclasses import dataclass
from typing import Literal

from django.conf import settings
from django.db.models import Prefetch, Q

from app.models import Draft, DraftTeam, HeroDraft, Team
from discordbot.activity_auth import ActivityIdentity, instance_pin, scope_allows
from discordbot.activity_intent import peek_intent
from discordbot.activity_roles import draft_role, involves_user
from discordbot.activity_targets import draft_tournament_id
from discordbot.models import DraftActivityChannel

ViewRef = dict
DraftKind = Literal["hero", "team"]
ViewKind = Literal["hero", "team", "bracket"]
Status = Literal["waiting", "drafting", "paused", "finished"]
InitialSource = Literal[
    "launch_intent", "involves_me", "channel_last", "instance_first"
]

FINISHED_HERO = {"completed", "abandoned"}
FINISHED_TEAM = {"completed"}

_HERO_STATUS: dict[str, Status] = {
    "waiting_for_captains": "waiting",
    "rolling": "waiting",
    "choosing": "waiting",
    "drafting": "drafting",
    "resuming": "drafting",
    "paused": "paused",
    "completed": "finished",
    "abandoned": "finished",
}
_TEAM_STATUS: dict[str, Status] = {
    "pending": "waiting",
    "drafting": "drafting",
    "resuming": "drafting",
    "paused": "paused",
    "completed": "finished",
}


def hero_status(state: str) -> Status:
    return _HERO_STATUS.get(state, "waiting")


def team_status(state: str) -> Status:
    return _TEAM_STATUS.get(state, "waiting")


def _draft_teams_prefetch() -> Prefetch:
    return Prefetch(
        "draft_teams",
        queryset=DraftTeam.objects.nocache()
        .select_related("tournament_team")
        .order_by("pk"),
    )


def hero_label(draft: HeroDraft) -> str:
    game = draft.game
    names = [dt.tournament_team.name for dt in draft.draft_teams.all()]
    names += ["TBD"] * (2 - len(names))
    return f"{game.get_bracket_type_display()} R{game.round} · {names[0]} vs {names[1]}"


def external_path(
    kind: ViewKind, view_id: int | None, tournament_id: int | None
) -> str:
    if kind == "hero":
        return f"/herodraft/{view_id}"
    if kind == "team":
        return f"/tournament/{tournament_id}/teams/draft"
    return f"/tournament/{tournament_id}/bracket"


def _load_draft(kind: DraftKind, draft_id: int) -> HeroDraft | Draft | None:
    if kind == "hero":
        return (
            HeroDraft.objects.nocache()
            .select_related("game__tournament")
            .prefetch_related(_draft_teams_prefetch())
            .filter(pk=draft_id)
            .first()
        )
    return (
        Draft.objects.nocache().select_related("tournament").filter(pk=draft_id).first()
    )


def notice_for(
    kind: DraftKind, draft_id: int, intent_id: str | None
) -> dict[str, object] | None:
    draft = _load_draft(kind, draft_id)
    if draft is None:
        return None
    tournament_id = draft_tournament_id(draft)
    if isinstance(draft, HeroDraft):
        tournament = draft.game.tournament
        label = hero_label(draft)
    else:
        tournament = draft.tournament
        label = "Team draft"
    notice: dict[str, object] = {
        "kind": kind,
        "draft_id": draft_id,
        "tournament_name": None if tournament is None else tournament.name,
        "label": label,
        "url": settings.SITE_URL + external_path(kind, draft_id, tournament_id),
    }
    if intent_id is not None:
        notice = {"intent_id": intent_id, **notice}
    return notice


def _is_live(draft: HeroDraft | Draft) -> bool:
    if isinstance(draft, HeroDraft):
        return draft.state not in FINISHED_HERO
    return draft.state not in FINISHED_TEAM


def live_drafts_involving(identity: ActivityIdentity) -> list[ViewRef]:
    user = identity.user
    tournament_id = identity.tournament_id
    if tournament_id is None:
        pin = identity.pin
        if pin is None:
            return []
        draft = _load_draft(pin["kind"], pin["draft"])
        if (
            draft is None
            or not _is_live(draft)
            or not involves_user(draft_role(user, pin["kind"], pin["draft"]))
        ):
            return []
        return [{"kind": pin["kind"], "id": pin["draft"]}]
    refs: list[ViewRef] = []
    on_team = Q(captain=user) | Q(members=user)
    team_drafts = (
        Draft.objects.nocache()
        .filter(tournament_id=tournament_id)
        .exclude(state__in=FINISHED_TEAM)
    )
    if (
        team_drafts.exists()
        and Team.objects.nocache().filter(on_team, tournament_id=tournament_id).exists()
    ):
        refs += [
            {"kind": "team", "id": pk}
            for pk in team_drafts.values_list("pk", flat=True)
        ]
    hero_ids = (
        HeroDraft.objects.nocache()
        .filter(game__tournament_id=tournament_id)
        .exclude(state__in=FINISHED_HERO)
        .filter(
            Q(draft_teams__tournament_team__captain=user)
            | Q(draft_teams__tournament_team__members=user)
        )
        .values_list("pk", flat=True)
        .distinct()
        .order_by("pk")
    )
    refs += [{"kind": "hero", "id": pk} for pk in hero_ids]
    return refs


@dataclass
class InitialView:
    view: ViewRef | None
    source: InitialSource
    launch_intent: dict | None
    notice: dict | None


def _channel_draft(
    identity: ActivityIdentity,
) -> tuple[DraftKind, HeroDraft | Draft] | None:
    instance = identity.instance
    binding = (
        DraftActivityChannel.objects.nocache()
        .select_related("draft__game", "team_draft")
        .filter(guild_id=instance.guild_id, channel_id=instance.channel_id)
        .first()
    )
    if binding is None:
        return None
    if binding.draft is not None:
        return "hero", binding.draft
    if binding.team_draft is not None:
        return "team", binding.team_draft
    return None


def resolve_initial_view(
    identity: ActivityIdentity, discord_user_id: str
) -> InitialView:
    instance = identity.instance
    notice: dict | None = None
    intent = peek_intent(discord_user_id)
    if intent is not None and intent.applies_to(instance.guild_id, instance.channel_id):
        if scope_allows(identity, intent.kind, intent.draft_id):
            return InitialView(
                view={"kind": intent.kind, "id": intent.draft_id},
                source="launch_intent",
                launch_intent=intent.ref(),
                notice=None,
            )
        notice = notice_for(intent.kind, intent.draft_id, intent.intent_id)
    involved = live_drafts_involving(identity)
    if len(involved) == 1:
        return InitialView(
            view=involved[0], source="involves_me", launch_intent=None, notice=notice
        )
    channel = _channel_draft(identity)
    if channel is not None:
        kind, draft = channel
        if scope_allows(identity, kind, draft.pk):
            return InitialView(
                view={"kind": kind, "id": draft.pk},
                source="channel_last",
                launch_intent=None,
                notice=notice,
            )
        if (
            notice is None
            and _is_live(draft)
            and draft_tournament_id(draft) != identity.tournament_id
        ):
            notice = notice_for(kind, draft.pk, None)
    pin = instance_pin(instance)
    return InitialView(
        view={"kind": pin["kind"], "id": pin["draft"]},
        source="instance_first",
        launch_intent=None,
        notice=notice,
    )
