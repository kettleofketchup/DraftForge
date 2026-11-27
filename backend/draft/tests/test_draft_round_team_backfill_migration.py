import unittest
from datetime import UTC, datetime

from tournament.models import Team
from tournament.models.team_log import (
    ORIGINAL_CAPTAINCY_FIRST,
    with_captain_acquired_at,
)

# django-test-migrations is a dev dep; a stale CI image may lack it.
try:
    from django_test_migrations.contrib.unittest_case import MigratorTestCase
except ImportError as _import_error:  # pragma: no cover
    raise unittest.SkipTest(
        "django-test-migrations not installed — rebuild backend-dev image "
        "to pick up the new dev dep from pyproject.toml."
    ) from _import_error

PLAYED = datetime(2026, 11, 1, 18, 0, tzinfo=UTC)


class DraftRoundTeamBackfillMigrationTest(MigratorTestCase):
    """draft 0007: existing rounds get the team their captain leads."""

    migrate_from = ("draft", "0006_retarget_tournament_models")
    migrate_to = ("draft", "0007_draftround_drafting_team")

    def prepare(self) -> None:
        apps = self.old_state.apps
        User = apps.get_model("app", "CustomUser")
        Tournament = apps.get_model("tournament", "Tournament")
        HistTeam = apps.get_model("tournament", "Team")
        TeamLog = apps.get_model("tournament", "TeamLog")
        Draft = apps.get_model("draft", "Draft")
        DraftRound = apps.get_model("draft", "DraftRound")

        names = ("solo", "shared", "outgoing", "teamless", "cross")
        u = {n: User.objects.create(username=f"bf923_{n}").pk for n in names}
        self.users = u

        tournament = Tournament.objects.create(name="Backfill 923", date_played=PLAYED)
        other_tournament = Tournament.objects.create(
            name="Backfill 923 other", date_played=PLAYED
        )
        self.tournament_id = tournament.pk

        self.solo_team = HistTeam.objects.create(
            name="Solo", tournament=tournament, captain_id=u["solo"]
        ).pk
        self.eliminated = HistTeam.objects.create(
            name="Eliminated", tournament=tournament, captain_id=u["shared"]
        ).pk
        self.live = HistTeam.objects.create(
            name="Live", tournament=tournament, captain_id=u["shared"]
        ).pk
        TeamLog.objects.create(
            team_id=self.live,
            team_snapshot_id=self.live,
            tournament_id=tournament.pk,
            team_name="Live",
            via="web",
            action="replace_captain",
            target_user_id=u["shared"],
            details={
                "before": {"captain_id": u["outgoing"]},
                "after": {"captain_id": u["shared"]},
            },
        )
        self.own_cross_team = HistTeam.objects.create(
            name="Cross here", tournament=tournament, captain_id=u["cross"]
        ).pk
        self.foreign_cross_team = HistTeam.objects.create(
            name="Cross there", tournament=other_tournament, captain_id=u["cross"]
        ).pk
        HistTeam.objects.create(
            name="Foreign only", tournament=other_tournament, captain_id=u["teamless"]
        )

        draft = Draft.objects.create(tournament=tournament)
        Draft.objects.create(tournament=other_tournament)

        def make_round(pick: int, captain: str | None) -> int:
            return DraftRound.objects.create(
                draft=draft,
                captain_id=u[captain] if captain else None,
                pick_number=pick,
            ).pk

        self.rounds = {
            "solo": make_round(1, "solo"),
            "shared": make_round(2, "shared"),
            "teamless": make_round(3, "teamless"),
            "none": make_round(4, None),
            "cross": make_round(5, "cross"),
        }

    def _stored(self) -> dict[str, int | None]:
        DraftRound = self.new_state.apps.get_model("draft", "DraftRound")
        by_pk = {pk: name for name, pk in self.rounds.items()}
        return {
            by_pk[pk]: team_id
            for pk, team_id in DraftRound.objects.filter(
                pk__in=self.rounds.values()
            ).values_list("pk", "drafting_team_id")
        }

    def test_backfill(self) -> None:
        self.assertEqual(
            self._stored(),
            {
                "solo": self.solo_team,
                "shared": self.eliminated,
                "teamless": None,
                "none": None,
                "cross": self.own_cross_team,
            },
        )

    def test_shared_captain_matches_property_fallback(self) -> None:
        fallback = (
            with_captain_acquired_at(
                Team.objects.nocache().filter(
                    tournament_id=self.tournament_id, captain_id=self.users["shared"]
                )
            )
            .order_by(*ORIGINAL_CAPTAINCY_FIRST)
            .first()
        )
        self.assertIsNotNone(fallback)
        self.assertEqual(self._stored()["shared"], fallback.pk)

    def test_cross_tournament_team_not_used(self) -> None:
        HistTeam = self.new_state.apps.get_model("tournament", "Team")
        team_id = self._stored()["cross"]
        self.assertNotEqual(team_id, self.foreign_cross_team)
        self.assertEqual(
            HistTeam.objects.get(pk=team_id).tournament_id, self.tournament_id
        )
