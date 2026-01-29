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

from app.models import CustomUser, PositionsModel, Team, Tournament


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
        for i, mmr in enumerate([5000, 4000, 3000, 2000, 1000]):
            positions = PositionsModel.objects.create()
            user = CustomUser.objects.create(
                username=f"user_{i}",
                discordId=f"discord_{i}",
                mmr=mmr,
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
                mmr=5000 - (i * 100),
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
            mmr=5000,
            positions=self.positions,
        )
        self.positions2 = PositionsModel.objects.create()
        self.user2 = CustomUser.objects.create(
            username="user2",
            discordId="discord2",
            mmr=4000,
            positions=self.positions2,
        )
        self.positions3 = PositionsModel.objects.create()
        self.non_member = CustomUser.objects.create(
            username="non_member",
            discordId="discord3",
            mmr=3000,
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
