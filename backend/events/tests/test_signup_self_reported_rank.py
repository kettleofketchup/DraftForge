from datetime import date
from unittest.mock import patch

from rest_framework.test import APIClient

from app.models import CustomUser, GameType
from events.models import Event
from events.services import process_rsvp
from events.tests.base import EventTestCase
from org.models import OrgUser
from org.models_profiles import PlayerDeadlockProfile, PlayerDotaProfile


@patch("events.services.notify_signup_changed")
class SignupSelfReportedRankTests(EventTestCase):
    def _player(self) -> CustomUser:
        user = self.make_user()
        org_user = OrgUser.objects.get(user=user, organization=self.org)
        PlayerDotaProfile.objects.create(
            org_user=org_user,
            rank_status="active",
            rank_medal="Legend 3",
            mmr=3300,
            rank_screenshot="https://example.com/rank.png",
        )
        PlayerDeadlockProfile.objects.create(
            org_user=org_user, rank="Emissary 1", rank_date=date(2026, 10, 2)
        )
        return user

    def _row(self, event: Event, user: CustomUser) -> dict:
        api = APIClient()
        api.force_authenticate(self.admin)
        resp = api.get(f"/api/events/signups/?event={event.pk}")
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        rows = body["results"] if isinstance(body, dict) else body
        (row,) = [r for r in rows if r["user"] == user.pk]
        return row

    def test_deadlock_event_serves_deadlock_rank_not_dota_profile(
        self, _notify: object
    ) -> None:
        user = self._player()
        event = self.make_event(game_type=GameType.DEADLOCK)
        process_rsvp(event, user)
        row = self._row(event, user)
        self.assertIsNone(row["dota_profile"])
        self.assertEqual(row["self_reported_rank"], "Emissary 1")
        self.assertEqual(row["self_reported_rank_date"], "2026-10-02")
        self.assertEqual(row["suggested_mmr_range_source"], "fallback")

    def test_dota_event_serves_dota_profile_not_deadlock_rank(
        self, _notify: object
    ) -> None:
        user = self._player()
        event = self.make_event(game_type=GameType.DOTA2)
        process_rsvp(event, user)
        row = self._row(event, user)
        self.assertEqual(row["dota_profile"]["rank_medal"], "Legend 3")
        self.assertEqual(row["suggested_mmr"], 3300)
        self.assertIsNone(row["self_reported_rank"])
        self.assertIsNone(row["self_reported_rank_date"])

    def test_deadlock_event_without_deadlock_profile(self, _notify: object) -> None:
        user = self.make_user()
        event = self.make_event(game_type=GameType.DEADLOCK)
        process_rsvp(event, user)
        row = self._row(event, user)
        self.assertIsNone(row["dota_profile"])
        self.assertIsNone(row["self_reported_rank"])
        self.assertIsNone(row["self_reported_rank_date"])
