"""Shared fixture for team-draft timer tests."""

from datetime import date, datetime, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate

from app.functions import teamdraft
from app.functions.teamdraft_timeout import skip_turn
from app.functions.teamdraft_views import teamdraft_pause
from app.functions.tournament import pick_player_for_round, undo_last_pick
from app.models import (
    CustomUser,
    Draft,
    DraftEvent,
    DraftOptions,
    DraftRound,
    League,
    Organization,
    Team,
    Tournament,
)
from org.models import OrgUser

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
                OrgUser.objects.create(user=captain, organization=org, mmr=mmr)

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
