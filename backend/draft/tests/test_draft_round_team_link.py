"""DraftRound.team prefers the stored drafting team over the captain lookup."""

from django.db import connection
from django.db.models import Max
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser
from draft.models import Draft, DraftRound
from draft.serializers.team import DraftRoundSerializer
from draft.services.shuffle import reassign_round_captain
from draft.tests.team_fixtures import TimedDraftFixture
from league.models import League
from org.models import Organization
from tournament.models import Team, Tournament
from tournament.models.team_log import TeamLogVia
from tournament.serializers.draft import DraftRoundForDraftSerializer
from tournament.services.team_management import replace_captain
from tournament.state import tournament_state_queryset
from user.tests.test_cacheops_integration import _redis_reachable


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

    def test_editing_round_captain_moves_the_round_to_their_team(self) -> None:
        rnd = self.make_round(self.cap_a, self.team_a)
        serializer = DraftRoundSerializer(
            rnd, data={"captain_id": self.cap_b.pk}, partial=True
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()

        rnd = self.fresh(rnd)
        self.assertEqual(rnd.captain_id, self.cap_b.pk)
        self.assertEqual(rnd.drafting_team_id, self.team_b.pk)

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


class BuildRoundsTeamTests(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(name="Build Org")
        self.league = League.objects.create(
            organization=self.org, name="Build League", steam_league_id=94002
        )
        self.tournament = Tournament.objects.create(
            name="Build Cup", date_played=timezone.now(), league=self.league
        )
        self.teams: list[Team] = []
        for order, name in enumerate(("a", "b", "c"), start=1):
            captain = CustomUser.objects.create_user(
                username=f"build_{name}", password="x"
            )
            self.tournament.users.add(captain)
            self.teams.append(
                Team.objects.create(
                    tournament=self.tournament,
                    name=f"Build {name}",
                    captain=captain,
                    draft_order=order,
                )
            )

    def test_build_rounds_stores_drafting_team(self) -> None:
        team_by_captain = {t.captain_id: t.pk for t in self.teams}
        for style in ("snake", "normal"):
            with self.subTest(draft_style=style):
                draft, _ = Draft.objects.update_or_create(
                    tournament=self.tournament, defaults={"draft_style": style}
                )
                draft.build_rounds()
                rounds = list(
                    DraftRound.objects.nocache()
                    .filter(draft=draft)
                    .select_related("drafting_team")
                )
                self.assertEqual(len(rounds), 4 * len(self.teams))
                for rnd in rounds:
                    self.assertEqual(
                        rnd.drafting_team_id, team_by_captain[rnd.captain_id]
                    )
                    self.assertEqual(
                        rnd.drafting_team.tournament_id, draft.tournament_id
                    )


class ShuffleTeamLinkTests(TestCase):
    def setUp(self) -> None:
        self.fx = TimedDraftFixture(
            style="shuffle",
            num_teams=3,
            timer_enabled=False,
            prefix="shl",
            captain_mmrs=[3000, 5000, 7000],
        )
        self.draft = self.fx.draft
        self.teams = self.fx.teams

    def rounds(self) -> list[DraftRound]:
        return list(
            DraftRound.objects.nocache()
            .filter(draft=self.draft)
            .order_by("pick_number")
        )

    def test_build_shuffle_rounds_first_round_has_team(self) -> None:
        first, *rest = self.rounds()
        self.assertEqual(first.captain_id, self.teams[0].captain_id)
        self.assertEqual(first.drafting_team_id, self.teams[0].pk)
        for rnd in rest:
            self.assertIsNone(rnd.captain_id)
            self.assertIsNone(rnd.drafting_team_id)

    def test_create_next_shuffle_round_sets_team(self) -> None:
        result = self.draft.create_next_shuffle_round()
        rnd = DraftRound.objects.nocache().get(pk=result["round"].pk)
        self.assertEqual(rnd.drafting_team_id, self.teams[0].pk)
        self.assertEqual(rnd.drafting_team_id, rnd.team.pk)

    def test_reassign_round_captain_replaces_team(self) -> None:
        rnd = self.rounds()[0]
        self.assertEqual(rnd.drafting_team_id, self.teams[0].pk)
        reassign_round_captain(self.draft, rnd, exclude_team_ids={self.teams[0].pk})
        fresh = DraftRound.objects.nocache().get(pk=rnd.pk)
        self.assertEqual(fresh.drafting_team_id, self.teams[1].pk)
        self.assertEqual(fresh.captain_id, self.teams[1].captain_id)

    def test_undo_resets_next_shuffle_round_team(self) -> None:
        first = self.rounds()[0]
        response = self.fx.pick(first, self.fx.staff, self.fx.players[0])
        self.assertEqual(response.status_code, 201, response.data)
        second = self.rounds()[1]
        self.assertIsNotNone(second.drafting_team_id)
        self.assertEqual(second.drafting_team.captain_id, second.captain_id)

        response = self.fx.undo(self.fx.staff)
        self.assertEqual(response.status_code, 200, response.data)
        second = self.rounds()[1]
        self.assertIsNone(second.captain_id)
        self.assertIsNone(second.drafting_team_id)


class TakeoverPickTests(TestCase):
    def setUp(self) -> None:
        self.fx = TimedDraftFixture(
            style="snake", num_teams=2, timer_enabled=False, prefix="tko"
        )
        self.draft = self.fx.draft
        self.live, self.eliminated = self.fx.teams
        self.old_captain = self.live.captain
        self.live_rounds = set(
            DraftRound.objects.nocache()
            .filter(draft=self.draft, captain=self.old_captain)
            .values_list("pk", flat=True)
        )
        self.player = self.fx.players[0]

    def take_over(self) -> None:
        Team.objects.filter(pk=self.eliminated.pk).invalidated_update(placement=2)
        change = replace_captain(
            self.live,
            self.eliminated.captain,
            actor=self.fx.staff,
            via=TeamLogVia.WEB,
            reason="r",
        )
        self.assertEqual(
            change.log.details["draft_rounds_skipped_reason"],
            "old_captain_leads_other_team",
        )

    def first_live_round(self) -> DraftRound:
        return (
            DraftRound.objects.nocache()
            .filter(pk__in=self.live_rounds)
            .order_by("pick_number")
            .first()
        )

    def member_pks(self, team: Team) -> set[int]:
        return set(
            Team.objects.nocache()
            .get(pk=team.pk)
            .members.nocache()
            .values_list("pk", flat=True)
        )

    def test_pick_player_after_shared_captain_takeover_adds_to_stored_team(
        self,
    ) -> None:
        self.take_over()
        rnd = self.first_live_round()
        self.assertEqual(rnd.captain_id, self.old_captain.pk)
        self.assertEqual(rnd.drafting_team_id, self.live.pk)

        rnd.pick_player(self.player)

        self.assertIn(self.player.pk, self.member_pks(self.live))
        self.assertNotIn(self.player.pk, self.member_pks(self.eliminated))

    def test_undo_after_takeover_uses_stored_team(self) -> None:
        self.take_over()
        self.first_live_round().pick_player(self.player)
        self.assertIn(self.player.pk, self.member_pks(self.live))

        response = self.fx.undo(self.fx.staff)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn(self.player.pk, self.member_pks(self.live))
        self.assertNotIn(self.player.pk, self.member_pks(self.eliminated))
        self.assertIsNone(self.first_live_round().choice_id)

    def payload_queries(self) -> tuple[int, list[int | None]]:
        state = tournament_state_queryset(fresh=True).get(pk=self.fx.tournament.pk)
        rounds = state.draft.draft_rounds.all()
        with CaptureQueriesContext(connection) as ctx:
            data = DraftRoundForDraftSerializer(rounds, many=True).data
        return len(ctx.captured_queries), [
            r["team"]["pk"] if r["team"] else None for r in data
        ]

    def test_state_payload_query_count_unchanged(self) -> None:
        linked_count, linked_teams = self.payload_queries()
        DraftRound.objects.filter(draft=self.draft).invalidated_update(
            drafting_team=None
        )
        null_count, null_teams = self.payload_queries()

        self.assertEqual(linked_teams, null_teams)
        self.assertNotIn(None, linked_teams)
        self.assertLessEqual(linked_count, null_count)


class TeamDeleteCacheTests(TransactionTestCase):
    def setUp(self) -> None:
        if not _redis_reachable():
            self.skipTest("Cacheops Redis not reachable")
        self.fx = TimedDraftFixture(
            style="snake", num_teams=2, timer_enabled=False, prefix="tdc"
        )
        self.draft = self.fx.draft
        self.kept, self.doomed = self.fx.teams

    def cached_rounds(self) -> dict[int, int | None]:
        return {
            r.pk: r.drafting_team_id
            for r in DraftRound.objects.filter(draft=self.draft)
        }

    def detail_teams(self, client: APIClient) -> dict[int, int | None]:
        response = client.get(f"/api/drafts/{self.draft.pk}/")
        self.assertEqual(response.status_code, 200)
        return {
            r["pk"]: r["team"]["pk"] if r["team"] else None
            for r in response.json()["draft_rounds"]
        }

    def test_team_delete_with_warm_cache_serializes(self) -> None:
        client = APIClient()
        before = self.cached_rounds()
        doomed_rounds = {pk for pk, t in before.items() if t == self.doomed.pk}
        kept_rounds = {pk for pk, t in before.items() if t == self.kept.pk}
        self.assertTrue(doomed_rounds)
        self.assertEqual(doomed_rounds | kept_rounds, set(before))
        self.detail_teams(client)

        self.doomed.delete()

        cached = self.cached_rounds()
        for pk in doomed_rounds:
            self.assertIsNone(cached[pk])
        for pk in kept_rounds:
            self.assertEqual(cached[pk], self.kept.pk)

        teams = self.detail_teams(client)
        for pk in doomed_rounds:
            self.assertIsNone(teams[pk])
        for pk in kept_rounds:
            self.assertEqual(teams[pk], self.kept.pk)

        fresh = dict(
            DraftRound.objects.nocache()
            .filter(draft=self.draft)
            .values_list("pk", "drafting_team_id")
        )
        for pk in doomed_rounds:
            self.assertIsNone(fresh[pk])
