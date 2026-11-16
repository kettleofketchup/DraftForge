from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser, League, Organization, Tournament
from events.models import Event
from org import activity

LOCMEM = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "test_activity_touch_points",
    }
}

APPLY = "org.activity.sync_org_discord_names.apply_async"


@override_settings(CACHES=LOCMEM)
class ActivityTouchPointsTest(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.user = CustomUser.objects.create_user(username="dragon", password="x")
        self.org = Organization.objects.create(
            name="DTX", discord_server_id="111", owner=self.user
        )
        self.org.admins.add(self.user)
        self.league = League.objects.create(
            name="Lg", organization=self.org, steam_league_id=4242
        )
        self.tournament = Tournament.objects.create(
            name="T",
            league=self.league,
            tournament_type="double_elimination",
            date_played=timezone.now(),
        )
        self.event_org = Organization.objects.create(
            name="EventOrg", discord_server_id="222"
        )
        start = timezone.now() + timedelta(days=1)
        self.event = Event.objects.create(
            organization=self.event_org,
            name="Ev",
            scheduled_at=start,
            ends_at=start + timedelta(hours=3),
            created_by=self.user,
        )
        self.event_tournament = Tournament.objects.create(
            name="ET",
            tournament_type="double_elimination",
            date_played=timezone.now(),
        )
        self.event.tournament = self.event_tournament
        self.event.save(update_fields=["tournament"])
        self.client = APIClient()
        apply_patch = mock.patch(APPLY)
        self.apply_async = apply_patch.start()
        self.addCleanup(apply_patch.stop)

    def _urls(self) -> list[tuple[str, int]]:
        return [
            (f"/api/organizations/{self.org.pk}/", self.org.pk),
            (f"/api/organizations/{self.org.pk}/users/", self.org.pk),
            (f"/api/leagues/{self.league.pk}/", self.org.pk),
            (f"/api/tournaments/{self.tournament.pk}/", self.org.pk),
            (f"/api/tournaments/{self.event_tournament.pk}/", self.event_org.pk),
            (f"/api/events/{self.event.pk}/", self.event_org.pk),
        ]

    def test_authenticated_get_marks_org_active(self) -> None:
        self.client.force_authenticate(self.user)
        for url, org_id in self._urls():
            with self.subTest(url=url):
                cache.clear()
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200, response.content)
                self.assertIsNotNone(cache.get(f"org_activity_{org_id}"))

    def test_anonymous_get_does_not_mark_org_active(self) -> None:
        for url, org_id in self._urls():
            if url.endswith("/users/"):
                continue
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200, response.content)
                self.assertIsNone(cache.get(f"org_activity_{org_id}"))
        self.apply_async.assert_not_called()

    def test_cache_hit_still_touches(self) -> None:
        self.client.force_authenticate(self.user)
        for url, org_id in self._urls():
            with self.subTest(url=url):
                with (
                    mock.patch(
                        "app.views_main.touch_org_activity",
                        wraps=activity.touch_org_activity,
                    ) as main_spy,
                    mock.patch(
                        "events.views.touch_org_activity",
                        wraps=activity.touch_org_activity,
                    ) as events_spy,
                ):
                    self.client.get(url)
                    self.client.get(url)
                calls = main_spy.call_args_list + events_spy.call_args_list
                self.assertEqual(len(calls), 2)
                self.assertEqual({call.args[1] for call in calls}, {org_id})

    def test_ssr_org_view_does_not_touch(self) -> None:
        self.client.force_authenticate(self.user)
        response = self.client.get(f"/api/organizations/{self.org.pk}/ssr/")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(cache.get(f"org_activity_{self.org.pk}"))
