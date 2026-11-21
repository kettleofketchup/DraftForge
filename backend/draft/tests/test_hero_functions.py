from datetime import date

from django.db import connection, reset_queries
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from app.models import CustomUser, Game, League, Team, Tournament
from app.serializers import tournament_organization
from draft.models import DraftTeam, HeroDraft
from draft.serializers.hero import HeroDraftSerializer
from draft.services.hero import build_draft_rounds
from draft.services.hero_state import herodraft_state_queryset
from org.models import Organization, OrgUser
from tests.cache import flush_run_cache


class BuildDraftRoundsTest(TestCase):
    def setUp(self):
        self.user1 = CustomUser.objects.create_user(
            username="captain1", password="test"
        )
        self.user2 = CustomUser.objects.create_user(
            username="captain2", password="test"
        )
        self.tournament = Tournament.objects.create(
            name="Test Tournament", date_played=date.today()
        )
        self.team1 = Team.objects.create(
            name="Team 1", tournament=self.tournament, captain=self.user1
        )
        self.team2 = Team.objects.create(
            name="Team 2", tournament=self.tournament, captain=self.user2
        )
        self.game = Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.team1,
            dire_team=self.team2,
        )

    def test_builds_24_rounds(self):
        """build_draft_rounds creates exactly 24 rounds."""
        draft = HeroDraft.objects.create(game=self.game)
        first_team = DraftTeam.objects.create(
            draft=draft, tournament_team=self.team1, is_first_pick=True
        )
        second_team = DraftTeam.objects.create(
            draft=draft, tournament_team=self.team2, is_first_pick=False
        )

        build_draft_rounds(draft, first_team, second_team)

        self.assertEqual(draft.rounds.count(), 24)

    def test_correct_sequence(self):
        """Rounds follow the updated Captain's Mode sequence."""
        draft = HeroDraft.objects.create(game=self.game)
        first_team = DraftTeam.objects.create(
            draft=draft, tournament_team=self.team1, is_first_pick=True
        )
        second_team = DraftTeam.objects.create(
            draft=draft, tournament_team=self.team2, is_first_pick=False
        )

        build_draft_rounds(draft, first_team, second_team)

        rounds = list(draft.rounds.all())

        # Verify first ban phase: F-F-S-S-F-S-S
        self.assertEqual(rounds[0].draft_team, first_team)
        self.assertEqual(rounds[0].action_type, "ban")
        self.assertEqual(rounds[1].draft_team, first_team)
        self.assertEqual(rounds[1].action_type, "ban")
        self.assertEqual(rounds[2].draft_team, second_team)
        self.assertEqual(rounds[3].draft_team, second_team)
        self.assertEqual(rounds[4].draft_team, first_team)
        self.assertEqual(rounds[5].draft_team, second_team)
        self.assertEqual(rounds[6].draft_team, second_team)

        # Verify first pick phase: F-S (rounds 8-9)
        self.assertEqual(rounds[7].action_type, "pick")
        self.assertEqual(rounds[7].draft_team, first_team)
        self.assertEqual(rounds[8].action_type, "pick")
        self.assertEqual(rounds[8].draft_team, second_team)

    def test_ban_and_pick_counts(self):
        """Both teams have 7 bans and 5 picks each."""
        draft = HeroDraft.objects.create(game=self.game)
        first_team = DraftTeam.objects.create(
            draft=draft, tournament_team=self.team1, is_first_pick=True
        )
        second_team = DraftTeam.objects.create(
            draft=draft, tournament_team=self.team2, is_first_pick=False
        )

        build_draft_rounds(draft, first_team, second_team)

        first_bans = draft.rounds.filter(
            draft_team=first_team, action_type="ban"
        ).count()
        first_picks = draft.rounds.filter(
            draft_team=first_team, action_type="pick"
        ).count()
        second_bans = draft.rounds.filter(
            draft_team=second_team, action_type="ban"
        ).count()
        second_picks = draft.rounds.filter(
            draft_team=second_team, action_type="pick"
        ).count()

        self.assertEqual(first_bans, 7)
        self.assertEqual(first_picks, 5)
        self.assertEqual(second_bans, 7)
        self.assertEqual(second_picks, 5)


class HeroDraftNameFieldsTest(TestCase):
    def setUp(self) -> None:
        flush_run_cache()
        self.owner = CustomUser.objects.create_user(username="hdn_owner", password="x")
        self.org = Organization.objects.create(name="HDN Org", owner=self.owner)
        self.league = League.objects.create(
            name="HDN League", organization=self.org, steam_league_id=77001
        )
        self._seq = 0

    def _draft(self, members_per_team: int, *, league: bool = True) -> HeroDraft:
        self._seq += 1
        tournament = Tournament.objects.create(
            name=f"HDN T{self._seq}",
            date_played=date.today(),
            league=self.league if league else None,
        )
        teams = []
        for side in ("a", "b"):
            captain = self._user(f"hdn{self._seq}_{side}_cap")
            team = Team.objects.create(
                name=f"HDN {self._seq}{side}", tournament=tournament, captain=captain
            )
            team.members.add(
                captain,
                *(
                    self._user(f"hdn{self._seq}_{side}_m{i}")
                    for i in range(members_per_team - 1)
                ),
            )
            teams.append(team)
        game = Game.objects.create(
            tournament=tournament, radiant_team=teams[0], dire_team=teams[1]
        )
        draft = HeroDraft.objects.create(game=game)
        for i, team in enumerate(teams):
            DraftTeam.objects.create(
                draft=draft, tournament_team=team, is_first_pick=i == 0
            )
        return draft

    def _user(self, username: str) -> CustomUser:
        user = CustomUser.objects.create_user(username=username, password="x")
        OrgUser.objects.update_or_create(
            user=user,
            organization=self.org,
            defaults={"guild_nickname": f"{username}_server"},
        )
        return user

    def _serialize(self, draft: HeroDraft) -> dict:
        return HeroDraftSerializer(herodraft_state_queryset().get(pk=draft.pk)).data

    def test_payload_carries_organization_pk(self) -> None:
        draft = self._draft(2)
        tournament = draft.game.tournament
        self.assertEqual(
            self._serialize(draft)["organization_pk"],
            tournament_organization(tournament).pk,
        )

    def test_organization_pk_is_none_without_an_org(self) -> None:
        draft = self._draft(2, league=False)
        self.assertIsNone(self._serialize(draft)["organization_pk"])

    def test_organization_pk_is_none_without_a_tournament(self) -> None:
        draft = self._draft(2)
        Game.objects.filter(pk=draft.game_id).update(tournament=None)
        self.assertIsNone(self._serialize(draft)["organization_pk"])

    def test_captain_and_members_carry_org_server_nickname(self) -> None:
        draft = self._draft(3)
        outsider = CustomUser.objects.create_user(username="hdn_outsider", password="x")
        team = draft.draft_teams.order_by("pk").first().tournament_team
        team.members.add(outsider)
        OrgUser.objects.filter(user=outsider).delete()

        data = self._serialize(draft)

        for draft_team in data["draft_teams"]:
            captain = draft_team["captain"]
            self.assertEqual(captain["guildNickname"], f"{captain['username']}_server")
            for member in draft_team["members"]:
                expected = (
                    None
                    if member["username"] == "hdn_outsider"
                    else f"{member['username']}_server"
                )
                self.assertEqual(member["guildNickname"], expected)

    def test_roll_winner_carries_server_nickname(self) -> None:
        draft = self._draft(2)
        winner = draft.draft_teams.order_by("pk").first()
        HeroDraft.objects.filter(pk=draft.pk).update(roll_winner=winner)
        data = self._serialize(draft)
        captain = data["roll_winner"]["captain"]
        self.assertEqual(captain["guildNickname"], f"{captain['username']}_server")

    def test_query_count_does_not_grow_with_members(self) -> None:
        small = self._draft(2)
        large = self._draft(10)
        counts = []
        for draft in (small, large):
            reset_queries()
            with CaptureQueriesContext(connection) as ctx:
                self._serialize(draft)
            counts.append(len(ctx.captured_queries))
        self.assertEqual(counts[0], counts[1])
