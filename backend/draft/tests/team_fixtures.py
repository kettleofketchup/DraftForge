"""Shared fixtures and helpers for team-draft tests."""

import json
from collections.abc import Callable
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, reset_queries, transaction
from django.db.models import QuerySet
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate

from app.models import CustomUser
from app.user_cache import serialize_user_core
from draft.models import Draft, DraftEvent, DraftOptions, DraftRound
from draft.services import team as teamdraft
from draft.services.team_timeout import skip_turn
from draft.views.team import teamdraft_pause
from draft.views.team_picks import pick_player_for_round, undo_last_pick
from league.models import League
from org.models import Organization
from tests.populate.utils import ensure_org_user
from tournament.models import Team, Tournament
from tournament.serializers.users import (
    collect_org_mmr,
    collect_tournament_user_pks,
    tournament_organization,
)

User = get_user_model()


class TimedDraftFixture:
    """4 teams × 5 users, Draft built, optional DraftOptions; timer tests build on this."""

    def __init__(
        self,
        *,
        style: str = "snake",
        num_teams: int = 4,
        timer_enabled: bool = True,
        grace_time_ms: int = 30000,
        reserve_time_ms: int = 30000,
        prefix: str = "td",
        captain_mmrs: list[int] | None = None,
    ) -> None:
        self.factory = APIRequestFactory()
        self.tournament: Tournament = Tournament.objects.create(
            name=f"{prefix} tournament", date_played=date.today()
        )
        users = [
            User.objects.create_user(username=f"{prefix}_u{i}", password="x")
            for i in range(num_teams * 5)
        ]
        self.tournament.users.set(users)
        self.teams: list[Team] = []
        for i in range(num_teams):
            team = Team.objects.create(
                tournament=self.tournament,
                name=f"T{i + 1}",
                captain=users[i * 5],
                draft_order=i + 1,
            )
            team.members.add(users[i * 5])
            self.teams.append(team)
        self.captains: list[CustomUser] = [t.captain for t in self.teams]
        captain_ids = {c.pk for c in self.captains}
        self.players: list[CustomUser] = [u for u in users if u.pk not in captain_ids]
        self.staff: CustomUser = User.objects.create_user(
            username=f"{prefix}_staff", password="x", is_staff=True
        )

        if captain_mmrs is not None:
            org = Organization.objects.create(name=f"{prefix} org")
            league = League.objects.create(
                organization=org, name=f"{prefix} league", steam_league_id=None
            )
            self.tournament.league = league
            self.tournament.save()
            for captain, mmr in zip(self.captains, captain_mmrs):
                ensure_org_user(captain, org, mmr=mmr)

        self.options: DraftOptions = DraftOptions.ensure_for(
            self.tournament,
            timer_enabled=timer_enabled,
            grace_time_ms=grace_time_ms,
            reserve_time_ms=reserve_time_ms,
        )
        self.draft: Draft = Draft.objects.create(
            tournament=self.tournament, draft_style=style
        )
        self.draft.build_rounds()

    def start(self, *, now: datetime | None = None) -> DraftRound:
        with transaction.atomic():
            return teamdraft.start_draft(
                self.draft, self.options, now=now or timezone.now()
            )

    def round(self, pick_number: int) -> DraftRound:
        return DraftRound.objects.nocache().get(
            draft=self.draft, pick_number=pick_number
        )

    def team_of(self, captain: CustomUser) -> Team:
        return Team.objects.nocache().get(tournament=self.tournament, captain=captain)

    def pick(
        self,
        round: DraftRound,
        actor: CustomUser,
        player: CustomUser | None = None,
        **body: object,
    ) -> Response:
        if player is None:
            player = self.draft.users_remaining.first()
        request = self.factory.post(
            "/api/tournaments/pick_player",
            {"draft_round_pk": round.pk, "user_pk": player.pk, **body},
            format="json",
        )
        force_authenticate(request, user=actor)
        return pick_player_for_round(request)

    def undo(self, actor: CustomUser) -> Response:
        request = self.factory.post(
            "/api/tournaments/undo-pick", {"draft_pk": self.draft.pk}, format="json"
        )
        force_authenticate(request, user=actor)
        return undo_last_pick(request)

    def populate_mid_draft(self, base: datetime) -> None:
        """Deterministic mid-draft state: roster extras, two picks, a skip, manual pause."""
        team0, team1, team2 = self.teams[0], self.teams[1], self.teams[2]
        team0.deputy_captain = self.players[-3]
        team0.save(update_fields=["deputy_captain"])
        team1.dropin_members.add(self.players[-1])
        team2.left_members.add(self.players[-2])
        step = iter(range(1, 100))

        def at() -> datetime:
            return base + timedelta(seconds=7 * next(step))

        with patch("django.utils.timezone.now", side_effect=at):
            self.start(now=base)
            for pick_number, player in ((1, self.players[0]), (2, self.players[1])):
                rnd = self.round(pick_number)
                self.pick(rnd, rnd.captain, player)
            active = self.draft.active_round
            active.timed_out_at = at()
            active.save(update_fields=["timed_out_at"])
            draft = Draft.objects.nocache().get(pk=self.draft.pk)
            with transaction.atomic():
                skip_turn(draft, DraftRound.objects.nocache().get(pk=active.pk))
            request = self.factory.post(f"/api/draft/{self.draft.pk}/pause/")
            force_authenticate(request, user=self.captains[0])
            teamdraft_pause(request, draft_pk=self.draft.pk)
        self.draft = Draft.objects.nocache().get(pk=self.draft.pk)

    def events(self, event_type: str) -> QuerySet[DraftEvent]:
        return DraftEvent.objects.nocache().filter(
            draft=self.draft, event_type=event_type
        )


MID_DRAFT_BASE: datetime = datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt_timezone.utc)
MMRS_4: list[int] = [1000, 2000, 3000, 4000]
MMRS_8: list[int] = [1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000]


def mid_draft_fixture(num_teams: int, prefix: str) -> TimedDraftFixture:
    mmrs = MMRS_4 if num_teams == 4 else MMRS_8
    fx = TimedDraftFixture(num_teams=num_teams, prefix=prefix, captain_mmrs=mmrs)
    fx.populate_mid_draft(MID_DRAFT_BASE)
    return fx


def legacy_users_dict(tournament: Tournament) -> dict:
    """Pre-optimisation build_users_dict: per-user cached core + MMR overlay."""
    seen_pks = collect_tournament_user_pks(tournament)
    org = tournament_organization(tournament)
    mmr_map = collect_org_mmr(tournament, org, seen_pks, fresh=False)
    is_org = org is not None
    result: dict = {}
    for pk in seen_pks:
        core = serialize_user_core(pk)
        if not core:
            continue
        if is_org:
            entry = dict(core)
            entry.update(mmr_map.get(pk, {}))
        else:
            entry = dict(core)
        result[pk] = entry
    return result


def dumps(data: object) -> str:
    return json.dumps(data, cls=DjangoJSONEncoder)


class FakeChannelLayer:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def group_send(self, group: str, message: dict) -> None:
        self.messages.append(message)


def count_queries(fn: Callable[[], object]) -> int:
    # The query log is a capped deque; a full one makes every capture read 0.
    reset_queries()
    with CaptureQueriesContext(connection) as ctx:
        fn()
    return len(ctx.captured_queries)


def rename_team(team_pk: int) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE app_team SET name = %s WHERE id = %s", ["Renamed", team_pk]
        )
