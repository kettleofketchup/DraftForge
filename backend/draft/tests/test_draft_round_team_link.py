"""DraftRound.team prefers the stored drafting team over the captain lookup."""

from django.db.models import Max
from django.test import TestCase
from django.utils import timezone

from app.models import CustomUser
from draft.models import Draft, DraftRound
from league.models import League
from org.models import Organization
from tournament.models import Team, Tournament
from tournament.state import tournament_state_queryset


class DraftRoundTeamAccessorTests(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(name="Link Org")
        self.league = League.objects.create(
            organization=self.org, name="Link League", steam_league_id=94001
        )
        self.tournament = Tournament.objects.create(
            name="Link Cup", date_played=timezone.now(), league=self.league
        )
        self.cap_a = CustomUser.objects.create_user(username="link_a", password="x")
        self.cap_b = CustomUser.objects.create_user(username="link_b", password="x")
        self.team_a = Team.objects.create(
            tournament=self.tournament, name="Link A", captain=self.cap_a
        )
        self.team_b = Team.objects.create(
            tournament=self.tournament, name="Link B", captain=self.cap_b
        )
        self.draft = Draft.objects.create(tournament=self.tournament)

    def make_round(
        self, captain: CustomUser | None, drafting_team: Team | None
    ) -> DraftRound:
        return DraftRound.objects.create(
            draft=self.draft,
            captain=captain,
            drafting_team=drafting_team,
            pick_number=1,
        )

    def fresh(self, rnd: DraftRound) -> DraftRound:
        return DraftRound.objects.nocache().select_related("draft").get(pk=rnd.pk)

    def test_stored_team_wins_over_captain_lookup(self) -> None:
        rnd = self.fresh(self.make_round(self.cap_a, self.team_b))
        self.assertEqual(rnd.team.pk, self.team_b.pk)

    def test_stored_team_returns_prefetched_instance(self) -> None:
        self.make_round(self.cap_a, self.team_b)
        state = tournament_state_queryset(fresh=True).get(pk=self.tournament.pk)
        rnd = state.draft.draft_rounds.all()[0]
        prefetched_b = next(
            t
            for t in state._prefetched_objects_cache["teams"]
            if t.pk == self.team_b.pk
        )
        with self.assertNumQueries(0):
            self.assertIs(rnd.team, prefetched_b)

    def test_stale_stored_pk_falls_back_to_captain_lookup(self) -> None:
        stale_pk = Team.objects.aggregate(m=Max("pk"))["m"] + 1000
        rnd = self.fresh(self.make_round(self.cap_a, None))
        rnd.drafting_team_id = stale_pk
        self.assertEqual(rnd.team.pk, self.team_a.pk)

        rnd.captain = None
        self.assertIsNone(rnd.team)

    def test_stale_stored_pk_prefetched_falls_back_to_captain_lookup(self) -> None:
        stale_pk = Team.objects.aggregate(m=Max("pk"))["m"] + 1000
        self.make_round(self.cap_a, None)
        state = tournament_state_queryset(fresh=True).get(pk=self.tournament.pk)
        rnd = state.draft.draft_rounds.all()[0]
        rnd.drafting_team_id = stale_pk
        self.assertEqual(rnd.team.pk, self.team_a.pk)

    def test_null_stored_team_uses_captain_lookup(self) -> None:
        rnd = self.fresh(self.make_round(self.cap_a, None))
        self.assertEqual(rnd.team.pk, self.team_a.pk)

    def test_assign_team_sets_captain_and_team(self) -> None:
        rnd = DraftRound(draft=self.draft, pick_number=1)
        rnd.assign_team(self.team_b)
        self.assertEqual(rnd.captain_id, self.cap_b.pk)
        self.assertEqual(rnd.drafting_team_id, self.team_b.pk)

    def test_assign_team_none_clears_captain_and_team(self) -> None:
        rnd = self.make_round(self.cap_a, self.team_a)
        rnd.assign_team(None)
        self.assertIsNone(rnd.captain_id)
        self.assertIsNone(rnd.drafting_team_id)
        self.assertEqual(
            DraftRound.objects.nocache().get(pk=rnd.pk).drafting_team_id,
            self.team_a.pk,
        )
