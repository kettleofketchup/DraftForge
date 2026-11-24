"""Captain-to-team lookups when one user captains an eliminated and a live team."""

from datetime import timedelta

from django.db import transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser
from draft.models import Draft, DraftRound, TeamDraftState
from draft.serializers.team import DraftRoundSerializer
from draft.services.team import team_for_round
from events.constants import EventState, SignupStatus
from events.models import Event, EventSignup
from league.models import League
from org.feature_keys import FeatureKey
from org.features import set_org_feature
from org.leadership.lifecycle import snapshot_event
from org.models import Organization
from org.models_leadership import EventCaptain
from tests.populate.utils import ensure_org_user
from tournament.models import Team, Tournament
from tournament.models.team_log import TeamLogVia
from tournament.services.team_management import add_standin, replace_captain, sub_in


class TakeoverLookupFixture(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.org = Organization.objects.create(name="Takeover Org")
        self.league = League.objects.create(
            organization=self.org, name="Takeover League", steam_league_id=93001
        )
        self.tournament = Tournament.objects.create(
            name="Takeover Cup", date_played=timezone.now(), league=self.league
        )
        self.staff = CustomUser.objects.create_user(
            username="to_staff", password="x", is_staff=True, is_superuser=True
        )
        self.u = self.make_user("to_u", 5000)
        self.b = self.make_user("to_b", 3000)
        self.e_mate = self.make_user("to_e_mate", 2000)
        self.l_mate = self.make_user("to_l_mate", 2000)
        self.tournament.users.add(self.u, self.b, self.e_mate, self.l_mate)

    def make_user(self, username: str, mmr: int) -> CustomUser:
        user = CustomUser.objects.create_user(username=username, password="x")
        ensure_org_user(user, self.org, mmr=mmr)
        return user

    def make_team(self, name: str, captain: CustomUser, mate: CustomUser) -> Team:
        team = Team.objects.create(
            tournament=self.tournament, name=name, captain=captain
        )
        team.members.add(captain, mate)
        return team

    def build_teams(self, *, e_first: bool) -> tuple[Team, Team]:
        if e_first:
            e = self.make_team("Eliminated", self.u, self.e_mate)
            live = self.make_team("Live", self.b, self.l_mate)
        else:
            live = self.make_team("Live", self.b, self.l_mate)
            e = self.make_team("Eliminated", self.u, self.e_mate)
        Team.objects.filter(pk=e.pk).invalidated_update(placement=3)
        return e, live

    def take_over(self, *, e_first: bool) -> tuple[Team, Team]:
        e, live = self.build_teams(e_first=e_first)
        replace_captain(live, self.u, actor=self.staff, via=TeamLogVia.WEB, reason="r")
        self.assertEqual(Team.objects.nocache().get(pk=live.pk).captain_id, self.u.pk)
        self.assertEqual(Team.objects.nocache().get(pk=e.pk).captain_id, self.u.pk)
        return e, live

    def make_round(self) -> DraftRound:
        draft = Draft.objects.create(tournament=self.tournament)
        return DraftRound.objects.create(draft=draft, captain=self.u, pick_number=1)

    def fresh_round(self, rnd: DraftRound) -> DraftRound:
        return DraftRound.objects.nocache().select_related("draft").get(pk=rnd.pk)

    def prefetched_round(self, rnd: DraftRound) -> DraftRound:
        fresh = self.fresh_round(rnd)
        fresh.draft.tournament = (
            Tournament.objects.nocache()
            .prefetch_related("teams")
            .get(pk=self.tournament.pk)
        )
        return fresh


class DraftRoundTeamTests(TakeoverLookupFixture):
    def assert_round_team_is_original(self, *, e_first: bool, prefetched: bool) -> None:
        e, live = self.take_over(e_first=e_first)
        self.assertEqual(e.pk < live.pk, e_first)
        rnd = self.make_round()
        rnd = self.prefetched_round(rnd) if prefetched else self.fresh_round(rnd)
        self.assertEqual(rnd.team.pk, e.pk)
        self.assertEqual(DraftRoundSerializer(rnd).data["team"]["pk"], e.pk)

    def test_round_resolves_to_original_team_query_path_e_lower_pk(self) -> None:
        self.assert_round_team_is_original(e_first=True, prefetched=False)

    def test_round_resolves_to_original_team_query_path_e_higher_pk(self) -> None:
        self.assert_round_team_is_original(e_first=False, prefetched=False)

    def test_round_resolves_to_original_team_prefetched_path_e_lower_pk(self) -> None:
        self.assert_round_team_is_original(e_first=True, prefetched=True)

    def test_round_resolves_to_original_team_prefetched_path_e_higher_pk(self) -> None:
        self.assert_round_team_is_original(e_first=False, prefetched=True)

    def test_single_captaincy_prefetched_unchanged(self) -> None:
        e, _live = self.build_teams(e_first=False)
        rnd = self.prefetched_round(self.make_round())
        self.assertEqual(rnd.team.pk, e.pk)


class LiveLookupTests(TakeoverLookupFixture):
    def test_set_ready_dual_captain_toggles_live_team(self) -> None:
        e, live = self.take_over(e_first=True)
        draft = Draft.objects.create(
            tournament=self.tournament, state=TeamDraftState.PENDING
        )
        client = APIClient()
        client.force_authenticate(self.u)

        resp = client.post(
            f"/api/draft/{draft.pk}/ready/", {"ready": True}, format="json"
        )

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Team.objects.nocache().get(pk=live.pk).draft_is_ready)
        self.assertFalse(Team.objects.nocache().get(pk=e.pk).draft_is_ready)

    def test_team_for_round_dual_captain_picks_live_team(self) -> None:
        _e, live = self.take_over(e_first=True)
        rnd = self.make_round()
        self.assertEqual(team_for_round(rnd.draft, rnd).pk, live.pk)


class ProdPathTests(TakeoverLookupFixture):
    def admit(self, event: Event, *users: CustomUser) -> None:
        for user in users:
            EventSignup.objects.create(
                event=event, user=user, status=SignupStatus.APPROVED
            )

    def test_dual_captaincy_via_standin_sub_in_resolves_to_original(self) -> None:
        start = timezone.now() - timedelta(hours=4)
        event = Event.objects.create(
            organization=self.org,
            name="Takeover Night",
            scheduled_at=start,
            ends_at=start + timedelta(hours=3),
            state=EventState.IN_PROGRESS,
            created_by=self.staff,
            tournament=self.tournament,
        )
        set_org_feature(self.org, FeatureKey.LEADERSHIP, enabled=True, actor=None)
        self.admit(event, self.u, self.b, self.e_mate, self.l_mate)
        e, live = self.build_teams(e_first=False)
        self.assertLess(live.pk, e.pk)

        add_standin(live, self.u, actor=self.staff, via=TeamLogVia.WEB, reason="r")
        sub_in(
            live,
            self.u,
            self.b,
            actor=self.staff,
            via=TeamLogVia.WEB,
            reason="r",
        )
        self.assertEqual(Team.objects.nocache().get(pk=live.pk).captain_id, self.u.pk)
        self.assertEqual(Team.objects.nocache().get(pk=e.pk).captain_id, self.u.pk)

        rnd = self.make_round()
        self.assertEqual(self.fresh_round(rnd).team.pk, e.pk)
        self.assertEqual(self.prefetched_round(rnd).team.pk, e.pk)

        Event.objects.filter(pk=event.pk).update(state=EventState.COMPLETED)
        event.refresh_from_db()
        with transaction.atomic():
            snapshot_event(event, now=timezone.now())
        snap = EventCaptain.objects.nocache().get(event=event, captain__user=self.u)
        self.assertEqual(snap.team_id, e.pk)
        self.assertEqual(
            set(snap.teammates.values_list("user_id", flat=True)), {self.e_mate.pk}
        )
        self.assertFalse(
            EventCaptain.objects.nocache().filter(event=event, team=live).exists()
        )
