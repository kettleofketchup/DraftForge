"""
Tests for Team member removal signals.

Verifies:
- Captain succession when captain is removed
- Deputy captain clearing when deputy is removed
- Team deletion when last member is removed
- Cascade from tournament.users to team.members
"""

from django.test import TestCase
from django.utils import timezone

from app.models import (
    CustomUser,
    Game,
    League,
    Organization,
    PositionsModel,
    Team,
    TeamLog,
    Tournament,
)
from app.services.team_leadership import successor_after_removal
from app.services.team_signals import owning_team_audit
from org.models import OrgUser


class TeamMemberRemovalTests(TestCase):
    """Test team member removal and captain succession."""

    def setUp(self):
        """Create test tournament with team and members."""
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            tournament_type="single_elimination",
            date_played=timezone.now(),
        )

        # Create users with different MMRs
        self.users = []
        for i in range(5):
            positions = PositionsModel.objects.create()
            user = CustomUser.objects.create(
                username=f"user_{i}",
                discordId=f"discord_{i}",
                positions=positions,
            )
            self.users.append(user)

        self.tournament.users.set(self.users)

        # Create team with captain (highest MMR) and deputy (second highest)
        self.team = Team.objects.create(
            tournament=self.tournament,
            name="Test Team",
        )
        self.team.members.set(self.users)
        self.team.captain = self.users[0]  # 5000 MMR
        self.team.deputy_captain = self.users[1]  # 4000 MMR
        self.team.save()

    def test_captain_removed_deputy_promoted(self):
        """When captain is removed, deputy should be promoted."""
        captain = self.team.captain
        deputy = self.team.deputy_captain

        self.team.members.remove(captain)
        self.team.refresh_from_db()

        self.assertEqual(self.team.captain, deputy)
        self.assertIsNone(self.team.deputy_captain)

    def test_captain_removed_non_member_deputy_not_promoted(self):
        """A deputy who is not a member is never promoted to captain (#571)."""
        outsider = CustomUser.objects.create(
            username="outsider",
            discordId="discord_outsider",
            positions=PositionsModel.objects.create(),
        )
        Team.objects.filter(pk=self.team.pk).update(deputy_captain=outsider)
        self.team.refresh_from_db()

        self.team.members.remove(self.users[0])
        self.team.refresh_from_db()

        self.assertEqual(self.team.captain, self.users[1])
        self.assertIsNone(self.team.deputy_captain)

    def test_captain_and_deputy_removed_highest_mmr_promoted(self):
        """When both captain and deputy removed, highest MMR member becomes captain."""
        captain = self.team.captain
        deputy = self.team.deputy_captain
        third_highest = self.users[2]  # 3000 MMR

        self.team.members.remove(captain, deputy)
        self.team.refresh_from_db()

        self.assertEqual(self.team.captain, third_highest)
        self.assertIsNone(self.team.deputy_captain)

    def test_deputy_removed_captain_unchanged(self):
        """When deputy is removed, captain stays the same."""
        captain = self.team.captain
        deputy = self.team.deputy_captain

        self.team.members.remove(deputy)
        self.team.refresh_from_db()

        self.assertEqual(self.team.captain, captain)
        self.assertIsNone(self.team.deputy_captain)

    def test_regular_member_removed_no_change(self):
        """Removing regular member doesn't affect captain/deputy."""
        captain = self.team.captain
        deputy = self.team.deputy_captain
        regular = self.users[4]  # 1000 MMR

        self.team.members.remove(regular)
        self.team.refresh_from_db()

        self.assertEqual(self.team.captain, captain)
        self.assertEqual(self.team.deputy_captain, deputy)

    def test_last_member_removed_team_deleted(self):
        """When last member is removed, team is deleted."""
        team_pk = self.team.pk

        # Remove all members
        self.team.members.clear()

        # Team should be deleted
        self.assertFalse(Team.objects.filter(pk=team_pk).exists())

    def test_no_dangling_teams_after_member_clear(self):
        """No teams should exist with zero members."""
        # Create multiple teams
        teams = [self.team]
        for i in range(3):
            team = Team.objects.create(
                tournament=self.tournament,
                name=f"Team {i}",
            )
            team.members.set(self.users[:2])
            team.captain = self.users[0]
            team.save()
            teams.append(team)

        # Clear all members from all teams
        for team in teams:
            team.members.clear()

        # No teams should exist
        self.assertEqual(Team.objects.filter(tournament=self.tournament).count(), 0)


class TournamentUserRemovalCascadeTests(TestCase):
    """Test cascade from tournament.users removal to team.members."""

    def setUp(self):
        """Create test tournament with teams."""
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            tournament_type="single_elimination",
            date_played=timezone.now(),
        )

        # Create users
        self.users = []
        for i in range(10):
            positions = PositionsModel.objects.create()
            user = CustomUser.objects.create(
                username=f"user_{i}",
                discordId=f"discord_{i}",
                positions=positions,
            )
            self.users.append(user)

        self.tournament.users.set(self.users)

        # Create two teams
        self.team1 = Team.objects.create(
            tournament=self.tournament,
            name="Team 1",
        )
        self.team1.members.set(self.users[:5])
        self.team1.captain = self.users[0]
        self.team1.save()

        self.team2 = Team.objects.create(
            tournament=self.tournament,
            name="Team 2",
        )
        self.team2.members.set(self.users[5:])
        self.team2.captain = self.users[5]
        self.team2.save()

    def test_tournament_user_removal_cascades_to_team(self):
        """Removing user from tournament.users removes them from team.members."""
        user = self.users[2]  # Regular member of team1

        self.tournament.users.remove(user)

        self.team1.refresh_from_db()
        self.assertNotIn(user, self.team1.members.all())

    def test_tournament_captain_removal_triggers_succession(self):
        """Removing captain from tournament triggers captain succession."""
        captain = self.team1.captain
        second_highest = self.users[1]

        self.tournament.users.remove(captain)

        self.team1.refresh_from_db()
        self.assertEqual(self.team1.captain, second_highest)

    def test_tournament_all_team_users_removed_deletes_team(self):
        """Removing all team members from tournament deletes the team."""
        team1_pk = self.team1.pk
        team1_members = list(self.users[:5])

        self.tournament.users.remove(*team1_members)

        self.assertFalse(Team.objects.filter(pk=team1_pk).exists())
        # Team 2 should still exist
        self.assertTrue(Team.objects.filter(pk=self.team2.pk).exists())

    def test_no_dangling_teams_after_tournament_user_clear(self):
        """No teams should exist after clearing tournament.users."""
        self.tournament.users.clear()

        self.assertEqual(Team.objects.filter(tournament=self.tournament).count(), 0)


class TeamValidationTests(TestCase):
    """Test Team model validation."""

    def setUp(self):
        """Create test data."""
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            tournament_type="single_elimination",
            date_played=timezone.now(),
        )

        self.positions = PositionsModel.objects.create()
        self.user1 = CustomUser.objects.create(
            username="user1",
            discordId="discord1",
            positions=self.positions,
        )
        self.positions2 = PositionsModel.objects.create()
        self.user2 = CustomUser.objects.create(
            username="user2",
            discordId="discord2",
            positions=self.positions2,
        )
        self.positions3 = PositionsModel.objects.create()
        self.non_member = CustomUser.objects.create(
            username="non_member",
            discordId="discord3",
            positions=self.positions3,
        )

    def test_captain_must_be_member(self):
        """Validation fails if captain is not a member."""
        from django.core.exceptions import ValidationError

        team = Team.objects.create(
            tournament=self.tournament,
            name="Test Team",
        )
        team.members.set([self.user1, self.user2])
        team.captain = self.non_member  # Not in members!
        team.save()

        with self.assertRaises(ValidationError) as ctx:
            team.full_clean()

        self.assertIn("captain", ctx.exception.message_dict)

    def test_deputy_must_be_member(self):
        """Validation fails if deputy is not a member."""
        from django.core.exceptions import ValidationError

        team = Team.objects.create(
            tournament=self.tournament,
            name="Test Team",
        )
        team.members.set([self.user1, self.user2])
        team.captain = self.user1
        team.deputy_captain = self.non_member  # Not in members!
        team.save()

        with self.assertRaises(ValidationError) as ctx:
            team.full_clean()

        self.assertIn("deputy_captain", ctx.exception.message_dict)

    def test_deputy_cannot_be_captain(self):
        """Validation fails if deputy is same as captain."""
        from django.core.exceptions import ValidationError

        team = Team.objects.create(
            tournament=self.tournament,
            name="Test Team",
        )
        team.members.set([self.user1, self.user2])
        team.captain = self.user1
        team.deputy_captain = self.user1  # Same as captain!
        team.save()

        with self.assertRaises(ValidationError) as ctx:
            team.full_clean()

        self.assertIn("deputy_captain", ctx.exception.message_dict)

    def test_valid_captain_and_deputy(self):
        """Validation passes with valid captain and deputy."""
        team = Team.objects.create(
            tournament=self.tournament,
            name="Test Team",
        )
        team.members.set([self.user1, self.user2])
        team.captain = self.user1
        team.deputy_captain = self.user2
        team.save()

        # Should not raise
        team.full_clean()


def _make_user(name: str) -> CustomUser:
    return CustomUser.objects.create(
        username=name,
        discordId=f"discord_{name}",
        positions=PositionsModel.objects.create(),
    )


class EmptyTeamAuditTests(TestCase):
    def setUp(self) -> None:
        self.tournament = Tournament.objects.create(
            name="Audit Tournament",
            tournament_type="single_elimination",
            date_played=timezone.now(),
        )
        self.user = _make_user("solo")
        self.tournament.users.add(self.user)
        self.team = Team.objects.create(tournament=self.tournament, name="Solo Team")
        self.team.members.add(self.user)
        self.team.captain = self.user
        self.team.save()

    def test_referenced_empty_team_kept(self) -> None:
        Game.objects.create(tournament=self.tournament, radiant_team=self.team)

        self.team.members.remove(self.user)

        self.assertTrue(Team.objects.filter(pk=self.team.pk).exists())
        rows = TeamLog.objects.filter(team_snapshot_id=self.team.pk)
        self.assertEqual([row.action for row in rows], ["empty_team_kept"])
        row = rows.get()
        self.assertEqual(row.via, "system")
        self.assertEqual(row.team_id, self.team.pk)
        self.assertTrue(row.details["references"])
        self.assertEqual(row.details["before"]["member_ids"], [self.user.pk])

    def test_unreferenced_empty_team_deleted_with_row(self) -> None:
        old_pk = self.team.pk

        self.team.members.remove(self.user)

        self.assertFalse(Team.objects.filter(pk=old_pk).exists())
        row = TeamLog.objects.get(team_snapshot_id=old_pk)
        self.assertEqual(row.action, "team_deleted")
        self.assertEqual(row.via, "system")
        self.assertIsNone(row.team)
        self.assertEqual(row.team_name, "Solo Team")
        self.assertEqual(row.tournament_id, self.tournament.pk)
        self.assertEqual(row.details["before"]["member_ids"], [self.user.pk])

    def test_post_clear_referenced_team_kept(self) -> None:
        Game.objects.create(tournament=self.tournament, dire_team=self.team)

        self.team.members.clear()

        self.assertTrue(Team.objects.filter(pk=self.team.pk).exists())
        row = TeamLog.objects.get(team_snapshot_id=self.team.pk)
        self.assertEqual(row.action, "empty_team_kept")
        self.assertTrue(row.details["references"])
        self.assertEqual(row.details["before"]["member_ids"], [self.user.pk])

    def test_post_clear_unreferenced_team_deleted_with_row(self) -> None:
        old_pk = self.team.pk

        self.team.members.clear()

        self.assertFalse(Team.objects.filter(pk=old_pk).exists())
        row = TeamLog.objects.get(team_snapshot_id=old_pk)
        self.assertEqual(row.action, "team_deleted")
        self.assertEqual(row.details["before"]["member_ids"], [self.user.pk])

    def test_tournament_user_removal_keeps_referenced_team(self) -> None:
        Game.objects.create(tournament=self.tournament, radiant_team=self.team)

        self.tournament.users.remove(self.user)

        self.assertTrue(Team.objects.filter(pk=self.team.pk).exists())

    def test_no_rows_while_owned_but_referenced_team_still_kept(self) -> None:
        Game.objects.create(tournament=self.tournament, radiant_team=self.team)

        with owning_team_audit():
            self.team.members.remove(self.user)

        self.assertTrue(Team.objects.filter(pk=self.team.pk).exists())
        self.assertFalse(TeamLog.objects.exists())

    def test_no_rows_while_owned_unreferenced_team_deleted(self) -> None:
        old_pk = self.team.pk

        with owning_team_audit():
            self.team.members.remove(self.user)

        self.assertFalse(Team.objects.filter(pk=old_pk).exists())
        self.assertFalse(TeamLog.objects.exists())


class SuccessionAuditTests(TestCase):
    def setUp(self) -> None:
        self.tournament = Tournament.objects.create(
            name="Succession Tournament",
            tournament_type="single_elimination",
            date_played=timezone.now(),
        )
        self.users = [_make_user(f"succ_{i}") for i in range(4)]
        self.tournament.users.set(self.users)
        self.team = Team.objects.create(tournament=self.tournament, name="Succ Team")
        self.team.members.set(self.users)
        self.team.captain = self.users[0]
        self.team.deputy_captain = self.users[1]
        self.team.save()

    def test_tournament_user_removal_writes_system_succession(self) -> None:
        captain, deputy = self.users[0], self.users[1]

        self.tournament.users.remove(captain)

        self.team.refresh_from_db()
        self.assertEqual(self.team.captain, deputy)
        self.assertIsNone(self.team.deputy_captain)
        row = TeamLog.objects.get(team=self.team)
        self.assertEqual(row.action, "system_succession")
        self.assertEqual(row.via, "system")
        self.assertIsNone(row.actor)
        self.assertEqual(row.details["succession"], "deputy")
        self.assertEqual(row.details["before"]["captain_id"], captain.pk)
        self.assertIn(captain.pk, row.details["before"]["member_ids"])
        self.assertEqual(row.details["after"]["captain_id"], deputy.pk)
        self.assertIsNone(row.details["after"]["deputy_captain_id"])
        self.assertNotIn(captain.pk, row.details["after"]["member_ids"])

    def test_deputy_removal_writes_deputy_cleared_row(self) -> None:
        self.team.members.remove(self.users[1])

        row = TeamLog.objects.get(team=self.team)
        self.assertEqual(row.action, "system_succession")
        self.assertEqual(row.details["succession"], "deputy_cleared")

    def test_regular_member_removal_writes_no_row(self) -> None:
        self.team.members.remove(self.users[3])

        self.assertFalse(TeamLog.objects.exists())

    def test_reverse_remove_runs_succession(self) -> None:
        self.users[0].teams_as_member.remove(self.team)

        self.team.refresh_from_db()
        self.assertEqual(self.team.captain, self.users[1])
        row = TeamLog.objects.get(team=self.team)
        self.assertEqual(row.details["succession"], "deputy")

    def test_reverse_clear_keeps_referenced_empty_team(self) -> None:
        solo = Team.objects.create(tournament=self.tournament, name="Reverse Solo")
        solo.members.add(self.users[3])
        Game.objects.create(tournament=self.tournament, radiant_team=solo)

        self.users[3].teams_as_member.clear()

        self.assertTrue(Team.objects.filter(pk=solo.pk).exists())
        self.assertEqual(TeamLog.objects.get(team=solo).action, "empty_team_kept")
        self.assertNotIn(self.users[3], self.team.members.all())
        self.assertFalse(TeamLog.objects.filter(team=self.team).exists())

    def test_no_system_rows_while_owned(self) -> None:
        with owning_team_audit():
            self.team.members.remove(self.users[0])

        self.team.refresh_from_db()
        self.assertEqual(self.team.captain, self.users[1])
        self.assertFalse(TeamLog.objects.exists())


class SuccessorAfterRemovalTests(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(name="Succession Org")
        self.league = League.objects.create(
            name="Succession League", organization=self.org
        )
        self.tournament = Tournament.objects.create(
            name="Order Tournament",
            tournament_type="single_elimination",
            date_played=timezone.now(),
            league=self.league,
        )
        self.users = [_make_user(f"order_{i}") for i in range(4)]
        self.team = Team.objects.create(tournament=self.tournament, name="Order Team")
        self.team.members.set(self.users)
        Team.objects.filter(pk=self.team.pk).update(
            captain=self.users[0], deputy_captain=self.users[1]
        )
        self.team.refresh_from_db()

    def _remove_rows(self, *users: CustomUser) -> None:
        # Bypass the m2m signal so the helper sees the post-remove state.
        Team.members.through.objects.filter(
            team=self.team, customuser__in=users
        ).delete()

    def test_deputy_first(self) -> None:
        self._remove_rows(self.users[0])

        self.assertEqual(
            successor_after_removal(self.team, {self.users[0].pk}),
            (self.users[1], None, "deputy"),
        )

    def test_org_mmr_when_no_deputy(self) -> None:
        OrgUser.objects.create(user=self.users[2], organization=self.org, mmr=1000)
        OrgUser.objects.create(user=self.users[3], organization=self.org, mmr=5000)
        removed = {self.users[0].pk, self.users[1].pk}
        self._remove_rows(self.users[0], self.users[1])

        self.assertEqual(
            successor_after_removal(self.team, removed),
            (self.users[3], None, "org_mmr"),
        )

    def test_lowest_pk_without_org_users(self) -> None:
        removed = {self.users[0].pk, self.users[1].pk}
        self._remove_rows(self.users[0], self.users[1])

        self.assertEqual(
            successor_after_removal(self.team, removed),
            (self.users[2], None, "lowest_pk"),
        )

    def test_unchanged_when_leadership_kept(self) -> None:
        self._remove_rows(self.users[3])

        self.assertEqual(
            successor_after_removal(self.team, {self.users[3].pk}),
            (self.users[0], self.users[1], "unchanged"),
        )

    def test_deputy_cleared(self) -> None:
        self._remove_rows(self.users[1])

        self.assertEqual(
            successor_after_removal(self.team, {self.users[1].pk}),
            (self.users[0], None, "deputy_cleared"),
        )

    def test_ghost_deputy_not_promoted(self) -> None:
        outsider = _make_user("order_ghost")
        Team.objects.filter(pk=self.team.pk).update(deputy_captain=outsider)
        self.team.refresh_from_db()
        self._remove_rows(self.users[0])

        self.assertEqual(
            successor_after_removal(self.team, {self.users[0].pk}),
            (self.users[1], None, "lowest_pk"),
        )
