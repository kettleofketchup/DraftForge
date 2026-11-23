from datetime import timedelta
from typing import Any

from django.test import TestCase
from django.utils import timezone

from app.models import (
    LIVE_TEAM_FIRST,
    ORIGINAL_CAPTAINCY_FIRST,
    CustomUser,
    Team,
    TeamLog,
    TeamLogAction,
    TeamLogVia,
    Tournament,
    with_captain_acquired_at,
)


class TeamOrderingTests(TestCase):
    def setUp(self) -> None:
        self.tournament = Tournament.objects.create(
            name="Order Cup", date_played=timezone.now()
        )
        self.user = CustomUser.objects.create_user(username="order_u", password="x")
        self.other = CustomUser.objects.create_user(username="order_x", password="x")

    def make_log(
        self,
        team: Team,
        action: str,
        details: dict[str, Any] | None = None,
    ) -> TeamLog:
        if details is None:
            details = {
                "before": {"captain_id": self.other.pk},
                "after": {"captain_id": self.user.pk},
            }
        return TeamLog.objects.create(
            team=team,
            team_snapshot_id=team.pk,
            tournament_id=self.tournament.pk,
            team_name=team.name,
            via=TeamLogVia.WEB,
            action=action,
            target_user=self.user,
            details=details,
        )

    def ordered_captain_teams(self) -> list[Team]:
        qs = with_captain_acquired_at(
            Team.objects.nocache().filter(tournament=self.tournament, captain=self.user)
        )
        return list(qs.order_by(*ORIGINAL_CAPTAINCY_FIRST))

    def test_live_team_first_orders_unplaced_before_placed(self) -> None:
        placed = Team.objects.create(tournament=self.tournament, name="A", placement=4)
        live = Team.objects.create(tournament=self.tournament, name="B")

        ordered = list(
            Team.objects.nocache()
            .filter(tournament=self.tournament)
            .order_by(*LIVE_TEAM_FIRST)
        )

        self.assertEqual(ordered, [live, placed])

    def test_original_captaincy_first_prefers_team_without_takeover_log(
        self,
    ) -> None:
        taken = Team.objects.create(
            tournament=self.tournament, name="L", captain=self.user
        )
        original = Team.objects.create(
            tournament=self.tournament, name="E", captain=self.user, placement=3
        )
        self.make_log(taken, TeamLogAction.REPLACE_CAPTAIN)

        self.assertEqual(self.ordered_captain_teams()[0], original)

    def test_original_captaincy_first_older_log_wins(self) -> None:
        newer = Team.objects.create(
            tournament=self.tournament, name="N", captain=self.user
        )
        older = Team.objects.create(
            tournament=self.tournament, name="O", captain=self.user
        )
        old_log = self.make_log(older, TeamLogAction.SET_CAPTAIN)
        self.make_log(newer, TeamLogAction.REPLACE_CAPTAIN)
        TeamLog.objects.filter(pk=old_log.pk).update(
            created_at=timezone.now() - timedelta(days=1)
        )

        self.assertEqual(self.ordered_captain_teams(), [older, newer])

    def test_acquired_at_matches_any_action_by_snapshot(self) -> None:
        actions = [
            TeamLogAction.SUB_IN,
            TeamLogAction.MARK_DROPOUT,
            TeamLogAction.SYSTEM_SUCCESSION,
            TeamLogAction.LEGACY_PATCH,
            TeamLogAction.SET_CAPTAIN,
            TeamLogAction.REPLACE_CAPTAIN,
        ]
        for action in actions:
            with self.subTest(action=action):
                team = Team.objects.create(
                    tournament=self.tournament,
                    name=f"T-{action}",
                    captain=self.user,
                )
                self.make_log(team, action)
                annotated = with_captain_acquired_at(
                    Team.objects.nocache().filter(pk=team.pk)
                ).get()
                self.assertIsNotNone(annotated.captain_acquired_at)

                unchanged = Team.objects.create(
                    tournament=self.tournament,
                    name=f"U-{action}",
                    captain=self.user,
                )
                self.make_log(
                    unchanged,
                    action,
                    {
                        "before": {"captain_id": self.user.pk},
                        "after": {"captain_id": self.user.pk},
                    },
                )
                annotated = with_captain_acquired_at(
                    Team.objects.nocache().filter(pk=unchanged.pk)
                ).get()
                self.assertIsNone(annotated.captain_acquired_at)

    def test_acquired_at_counts_takeover_from_no_captain(self) -> None:
        team = Team.objects.create(
            tournament=self.tournament, name="Empty", captain=self.user
        )
        self.make_log(
            team,
            TeamLogAction.SYSTEM_SUCCESSION,
            {"before": {"captain_id": None}, "after": {"captain_id": self.user.pk}},
        )

        annotated = with_captain_acquired_at(
            Team.objects.nocache().filter(pk=team.pk)
        ).get()

        self.assertIsNotNone(annotated.captain_acquired_at)

    def test_acquired_at_ignores_logs_for_other_captains(self) -> None:
        team = Team.objects.create(
            tournament=self.tournament, name="Other", captain=self.user
        )
        self.make_log(
            team,
            TeamLogAction.SET_CAPTAIN,
            {
                "before": {"captain_id": self.user.pk},
                "after": {"captain_id": self.other.pk},
            },
        )

        annotated = with_captain_acquired_at(
            Team.objects.nocache().filter(pk=team.pk)
        ).get()

        self.assertIsNone(annotated.captain_acquired_at)

    def test_replace_captain_choice_exists(self) -> None:
        self.assertEqual(TeamLogAction("replace_captain").label, "Replace Captain")
