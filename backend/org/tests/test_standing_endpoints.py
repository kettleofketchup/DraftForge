from django.test import override_settings
from rest_framework.test import APIClient

from app.models import CustomUser
from org.conduct.constants import Outcome
from org.feature_keys import FeatureKey
from org.features import set_org_feature
from org.models_conduct import OrgConductSettings
from org.tests.conduct_base import ConductTestCase


@override_settings(CACHEOPS_ENABLED=False)
class StandingEndpointsTest(ConductTestCase):
    def setUp(self) -> None:
        self.unlock()
        set_org_feature(self.org, FeatureKey.CONTRIBUTIONS, enabled=True, actor=None)
        self.member = self.make_user()
        for _ in range(3):
            self.outcome(self.member, outcome=Outcome.ATTENDED)

    def url(self, track: str, query: str = "") -> str:
        return f"/api/organizations/{self.org.pk}/standing/{track}/leaderboard/{query}"

    def get(self, url: str, user: CustomUser | None = None) -> object:
        client = APIClient()
        if user is not None:
            client.force_authenticate(user)
        return client.get(url)

    def test_tracks_lists_enabled_tracks(self) -> None:
        response = self.get(
            f"/api/organizations/{self.org.pk}/standing/tracks/", self.member
        )
        self.assertEqual(response.status_code, 200)
        keys = [t["key"] for t in response.data["tracks"]]
        self.assertEqual(keys, ["contribution", "conduct"])
        conduct = response.data["tracks"][1]
        self.assertEqual(conduct["metrics"][0]["key"], "show_rate")
        self.assertFalse(conduct["metrics"][0]["periodic"])

    def private(self) -> None:
        OrgConductSettings.objects.create(
            organization=self.org, leaderboard_public=False
        )

    def test_private_conduct_board_refuses_outsiders(self) -> None:
        self.private()
        anon = self.get(self.url("conduct"))
        self.assertEqual(
            anon.json()["detail"], "Authentication credentials were not provided."
        )
        outsider = CustomUser.objects.create_user(username="outsider", password="x")
        self.assertEqual(self.get(self.url("conduct"), outsider).status_code, 403)

    def test_member_sees_own_row_only_on_private_board(self) -> None:
        self.private()
        response = self.get(self.url("conduct"), self.member)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["rows_visible"])
        self.assertEqual(response.data["rows"], [])
        self.assertAlmostEqual(response.data["own_row"]["value"], 0.925, places=3)
        self.assertEqual(response.data["period"], "current")

    def test_staff_sees_rows(self) -> None:
        response = self.get(self.url("conduct"), self.admin)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["rows_visible"])
        self.assertEqual(len(response.data["rows"]), 1)
        self.assertEqual(response.data["rows"][0]["sample"], 3)

    def test_public_board_lets_outsider_in_without_rows(self) -> None:
        OrgConductSettings.objects.create(
            organization=self.org, leaderboard_public=True
        )
        outsider = CustomUser.objects.create_user(username="outsider2", password="x")
        response = self.get(self.url("conduct"), outsider)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["rows"], [])
        self.assertIsNone(response.data["own_row"])

    def test_unknown_track_and_metric(self) -> None:
        self.assertEqual(self.get(self.url("nope"), self.admin).status_code, 404)
        response = self.get(self.url("conduct", "?metric=points"), self.admin)
        self.assertEqual(response.status_code, 400)

    def test_locked_track(self) -> None:
        set_org_feature(self.org, FeatureKey.CONDUCT, enabled=False, actor=None)
        self.assertEqual(self.get(self.url("conduct"), self.admin).status_code, 403)

    def test_contribution_board_anonymous_sees_total(self) -> None:
        response = self.get(self.url("contribution"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["rows"], [])
        self.assertEqual(response.data["total"], 0)
