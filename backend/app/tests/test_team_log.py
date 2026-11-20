"""TeamLog audit rows outlive their team and stay read-only in admin."""

from django.conf import settings
from django.contrib import admin
from django.test import RequestFactory, TestCase
from django.utils import timezone

from app.models import (
    CustomUser,
    Team,
    TeamLog,
    TeamLogAction,
    TeamLogVia,
    Tournament,
)


class TeamLogModelTests(TestCase):
    def setUp(self) -> None:
        self.tournament = Tournament.objects.create(
            name="Log Cup", date_played=timezone.now()
        )
        self.team = Team.objects.create(tournament=self.tournament, name="Loggers")

    def make_log(self) -> TeamLog:
        return TeamLog.objects.create(
            team=self.team,
            team_snapshot_id=self.team.pk,
            tournament_id=self.tournament.pk,
            team_name=self.team.name,
            via=TeamLogVia.WEB,
            action=TeamLogAction.RENAME,
        )

    def test_log_survives_team_delete(self) -> None:
        log = self.make_log()
        team_pk = self.team.pk

        self.team.delete()

        log.refresh_from_db()
        self.assertIsNone(log.team)
        self.assertEqual(log.team_snapshot_id, team_pk)
        self.assertEqual(log.team_name, "Loggers")

    def test_defaults(self) -> None:
        log = self.make_log()

        self.assertEqual(log.override_rules, [])
        self.assertEqual(log.details, {})
        self.assertEqual(log.reason, "")
        self.assertIn(log, self.team.logs.all())

    def test_not_cached(self) -> None:
        self.assertNotIn("app.teamlog", settings.CACHEOPS)

    def test_admin_read_only(self) -> None:
        superuser = CustomUser.objects.create_user(
            username="log_admin", password="test", is_staff=True, is_superuser=True
        )
        request = RequestFactory().get("/admin/app/teamlog/")
        request.user = superuser
        model_admin = admin.site._registry[TeamLog]
        log = self.make_log()

        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request, log))
        self.assertFalse(model_admin.has_delete_permission(request, log))
