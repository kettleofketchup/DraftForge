from typing import Any

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser
from org.conduct.constants import Outcome
from org.feature_keys import FeatureKey
from org.features import set_org_feature
from org.models import ContributionEntry
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

    def get(self, url: str, user: CustomUser | None = None) -> Any:
        client = APIClient()
        if user is not None:
            client.force_authenticate(user)
        return client.get(url)

    def private(self) -> None:
        OrgConductSettings.objects.create(
            organization=self.org, leaderboard_public=False
        )

    def entry(self, user: CustomUser, points: int) -> None:
        ContributionEntry.objects.create(
            organization=self.org,
            org_user=self.org_user(user),
            kind="manual",
            points=points,
            reason="thanks",
            occurred_at=timezone.now(),
        )

    def test_tracks_endpoint_lists_enabled_tracks(self) -> None:
        response = self.get(
            f"/api/organizations/{self.org.pk}/standing/tracks/", self.member
        )
        self.assertEqual(response.status_code, 200)
        keys = [t["key"] for t in response.data["tracks"]]
        self.assertEqual(keys, ["contribution", "conduct"])
        conduct = response.data["tracks"][1]
        self.assertEqual(conduct["metrics"][0]["key"], "show_rate")
        self.assertFalse(conduct["metrics"][0]["periodic"])
        self.assertEqual(
            set(conduct),
            {
                "key",
                "label",
                "metrics",
                "can_view_rows",
                "can_view_own",
                "board_open",
                "can_manage",
            },
        )

    def test_tracks_endpoint_skips_locked_and_404s_unknown_org(self) -> None:
        set_org_feature(self.org, FeatureKey.CONDUCT, enabled=False, actor=None)
        response = self.get(f"/api/organizations/{self.org.pk}/standing/tracks/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([t["key"] for t in response.data["tracks"]], ["contribution"])
        self.assertEqual(
            self.get("/api/organizations/999999/standing/tracks/").status_code, 404
        )

    def test_conduct_leaderboard_private_matrix(self) -> None:
        self.private()
        anon = self.get(self.url("conduct"))
        self.assertEqual(anon.status_code, 403)
        self.assertEqual(
            anon.json()["detail"], "Authentication credentials were not provided."
        )
        outsider = CustomUser.objects.create_user(username="outsider", password="x")
        self.assertEqual(self.get(self.url("conduct"), outsider).status_code, 403)

        member = self.get(self.url("conduct"), self.member)
        self.assertEqual(member.status_code, 200)
        self.assertFalse(member.data["rows_visible"])
        self.assertEqual(member.data["rows"], [])
        self.assertAlmostEqual(member.data["own_row"]["value"], 0.925, places=3)

        staff = self.get(self.url("conduct"), self.admin)
        self.assertEqual(staff.status_code, 200)
        self.assertTrue(staff.data["rows_visible"])
        self.assertEqual(len(staff.data["rows"]), 1)
        self.assertEqual(staff.data["rows"][0]["sample"], 3)

    def test_conduct_leaderboard_public_nonmember_rows_hidden(self) -> None:
        OrgConductSettings.objects.create(
            organization=self.org, leaderboard_public=True
        )
        outsider = CustomUser.objects.create_user(username="outsider2", password="x")
        response = self.get(self.url("conduct"), outsider)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["rows_visible"])
        self.assertEqual(response.data["rows"], [])
        self.assertIsNone(response.data["own_row"])

    def test_contribution_leaderboard_matches_legacy(self) -> None:
        self.entry(self.member, 5)
        self.entry(self.admin, 2)
        self.entry(self.admin, 1)
        legacy = self.get(
            f"/api/organizations/{self.org.pk}/contributions/leaderboard/", self.admin
        )
        generic = self.get(self.url("contribution"), self.admin)
        self.assertEqual(generic.status_code, 200)
        self.assertEqual(generic.data["total"], legacy.data["total"])
        self.assertEqual(generic.data["period"], legacy.data["period"])
        self.assertEqual(generic.data["metric"]["key"], "points")
        self.assertEqual(
            [(r["member"]["org_user_pk"], r["value"]) for r in generic.data["rows"]],
            [(r["org_user_pk"], r["points"]) for r in legacy.data["rows"]],
        )

    def test_contribution_entries_metric(self) -> None:
        self.entry(self.member, 5)
        self.entry(self.admin, 2)
        self.entry(self.admin, 1)
        legacy = self.get(
            f"/api/organizations/{self.org.pk}/contributions/leaderboard/", self.admin
        )
        response = self.get(self.url("contribution", "?metric=entries"), self.admin)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["metric"]["key"], "entries")
        self.assertEqual(response.data["metric"]["format"], "int")
        entries = {r["org_user_pk"]: r["entries"] for r in legacy.data["rows"]}
        self.assertEqual(
            {r["member"]["org_user_pk"]: r["value"] for r in response.data["rows"]},
            entries,
        )
        self.assertEqual(
            [r["value"] for r in response.data["rows"]],
            sorted(entries.values(), reverse=True),
        )

    def test_unknown_track_404_unknown_metric_400_locked_403(self) -> None:
        self.assertEqual(self.get(self.url("nope"), self.admin).status_code, 404)
        response = self.get(self.url("conduct", "?metric=points"), self.admin)
        self.assertEqual(response.status_code, 400)
        set_org_feature(self.org, FeatureKey.CONDUCT, enabled=False, actor=None)
        locked = self.get(self.url("conduct"), self.admin)
        self.assertEqual(locked.status_code, 403)
        self.assertEqual(locked.data["code"], "feature_locked")

    def test_non_periodic_echoes_current(self) -> None:
        for query in ("", "?period=2026-01", "?period=all", "?period=garbage"):
            with self.subTest(query=query):
                response = self.get(self.url("conduct", query), self.admin)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["period"], "current")

    def test_periodic_metric_parses_period(self) -> None:
        response = self.get(self.url("contribution", "?period=2026-01"), self.admin)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["period"], "2026-01")
        bad = self.get(self.url("contribution", "?period=garbage"), self.admin)
        self.assertEqual(bad.status_code, 400)

    def test_contribution_board_anonymous_sees_total(self) -> None:
        response = self.get(self.url("contribution"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["rows"], [])
        self.assertEqual(response.data["total"], 0)
