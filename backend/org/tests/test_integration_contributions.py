"""Contribution-only live totals for the promotion integration.

GET ``/api/organizations/{org}/integration/v1/contributions/`` lists every
OrgUser of the org with their all-time ``contribution`` track total as a
signed decimal string. Leadership and conduct rows share the ledger table
and are excluded. A member without a canonical Discord ID cannot be mapped
to the external contact log, so it is ``unavailable`` with no points rather
than zero. Pages are
keyed on the OrgUser PK and their signed cursors bind the org and a
fingerprint of membership and identity, never the mutable points.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

from django.core.cache import cache
from django.db import OperationalError, connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser
from events.models import Event
from org.api_tokens.tokens import issue_token
from org.contributions.queries import leaderboard
from org.features import FeatureKey, set_org_feature
from org.integration.contributions import (
    _fingerprint,
    _membership,
    format_points,
    list_contribution_totals,
)
from org.integration.cursors import encode_cursor
from org.models import ContributionEntry, Organization, OrgUser, PromoSend
from org.standing import ledger
from org.standing.periods import parse_period
from org.tests.test_api_tokens import LOCMEM_CACHE

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
INT64_MAX = 2**63 - 1
INT64_MIN = -(2**63)
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z")


@override_settings(CACHES=LOCMEM_CACHE)
class _ContributionsBase(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.admin = CustomUser.objects.create_user(username="cx_admin", password="x")
        self.org = Organization.objects.create(name="Contrib Export Org")
        self.other_org = Organization.objects.create(name="Other Export Org")
        self.org.admins.add(self.admin)
        set_org_feature(self.org, FeatureKey.CONTRIBUTIONS, enabled=True, actor=None)
        self.issued = issue_token(
            self.org, self.admin, "adaptor", operations=["contributions:read"]
        )
        self.seq = 0

    def member(
        self,
        name: str,
        *,
        discord: str | None = "auto",
        org: Organization | None = None,
    ) -> OrgUser:
        self.seq += 1
        if discord == "auto":
            discord = str(123456789012340000 + self.seq)
        user = CustomUser.objects.create_user(
            username=name, password="x", discordId=discord
        )
        return OrgUser.objects.create(user=user, organization=org or self.org)

    def add(self, ou: OrgUser, points: int, *, kind: str = "manual") -> None:
        ledger.award(
            org=ou.organization,
            user=ou.user,
            kind=kind,
            points=points,
            occurred_at=NOW,
            reason="r",
        )

    def bearer(self, raw: str | None = None) -> APIClient:
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {raw or self.issued.raw}")
        return client

    def url(self, org: Organization | None = None) -> str:
        return (
            f"/api/organizations/{(org or self.org).pk}/integration/v1/contributions/"
        )

    def get(self, params: dict[str, Any] | None = None, **kwargs: Any):
        raw = kwargs.pop("raw", None)
        return self.bearer(raw).get(self.url(**kwargs), params or {})

    def all_pages(self, limit: int = 100) -> list[dict]:
        seen: list[dict] = []
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {"limit": limit}
            if cursor:
                params["cursor"] = cursor
            resp = self.get(params)
            self.assertEqual(resp.status_code, 200, resp.content)
            body = resp.json()
            seen.extend(body["members"])
            cursor = body["next_cursor"]
            if cursor is None:
                return seen

    def by_org_user(self, rows: list[dict]) -> dict[str, dict]:
        return {r["org_user_id"]: r for r in rows}

    def assertError(self, resp, status: int, code: str) -> None:
        self.assertEqual(resp.status_code, status, resp.content)
        self.assertEqual(resp.json()["error"]["code"], code)


class ShapeTests(_ContributionsBase):
    def test_response_shape_and_observed_at(self) -> None:
        ou = self.member("shape")
        self.add(ou, 18)
        body = self.get().json()
        self.assertEqual(
            set(body),
            {"source", "track", "period", "observed_at", "members", "next_cursor"},
        )
        self.assertEqual(body["source"], "draftforge")
        self.assertEqual(body["track"], "contribution")
        self.assertEqual(body["period"], "all_time")
        self.assertRegex(body["observed_at"], TIMESTAMP)
        self.assertIsNone(body["next_cursor"])
        self.assertEqual(
            body["members"],
            [
                {
                    "user_id": str(ou.user_id),
                    "org_user_id": str(ou.pk),
                    "discord_id": ou.user.discordId,
                    "status": "available",
                    "points": "18",
                }
            ],
        )

    def test_zero_negative_and_decreasing_absolute_totals(self) -> None:
        zero = self.member("zero")
        negative = self.member("negative")
        falling = self.member("falling")
        self.add(negative, 3)
        self.add(negative, -7)
        self.add(falling, 10)
        rows = self.by_org_user(self.all_pages())
        self.assertEqual(rows[str(zero.pk)]["points"], "0")
        self.assertEqual(rows[str(negative.pk)]["points"], "-4")
        self.assertEqual(rows[str(falling.pk)]["points"], "10")

        # A later decrease is reported as the new absolute total, not a delta.
        self.add(falling, -6)
        rows = self.by_org_user(self.all_pages())
        self.assertEqual(rows[str(falling.pk)]["points"], "4")
        self.assertEqual(rows[str(negative.pk)]["points"], "-4")

    def test_zero_totals_absent_from_leaderboard_are_exported(self) -> None:
        cancelled = self.member("cancelled")
        self.add(cancelled, 5)
        self.add(cancelled, -5)
        untouched = self.member("untouched")
        board = leaderboard(self.org, parse_period(self.org, None))
        self.assertNotIn(cancelled.pk, [r["org_user_pk"] for r in board])
        rows = self.by_org_user(self.all_pages())
        self.assertEqual(rows[str(cancelled.pk)]["points"], "0")
        self.assertEqual(rows[str(untouched.pk)]["points"], "0")

    def test_only_contribution_track(self) -> None:
        ou = self.member("tracks")
        self.add(ou, 3)
        self.add(ou, 5, kind="captained")  # leadership track
        ContributionEntry.objects.create(
            org_user=ou,
            organization=self.org,
            track="conduct",
            kind="conduct_row",
            points=11,
            occurred_at=NOW,
        )
        rows = self.by_org_user(self.all_pages())
        self.assertEqual(rows[str(ou.pk)]["points"], "3")

    def test_contacted_and_no_mmr_members_still_exported(self) -> None:
        # Plain members with no MMR, profile or contribution rows, and
        # members who have been contacted for promotion, are all exported.
        plain = self.member("plain")
        contacted = self.member("contacted")
        event = Event.objects.create(
            organization=self.org, name="E", scheduled_at=NOW, created_by=self.admin
        )
        PromoSend.objects.create(
            organization=self.org,
            event=event,
            recipient=contacted.user,
            sender=self.admin,
            text="hi",
        )
        rows = self.by_org_user(self.all_pages())
        self.assertEqual(rows[str(plain.pk)]["status"], "available")
        self.assertEqual(rows[str(contacted.pk)]["status"], "available")
        self.assertEqual(rows[str(contacted.pk)]["points"], "0")

    def test_missing_discord_is_unavailable_without_points(self) -> None:
        none = self.member("none", discord=None)
        empty = self.member("empty", discord="")
        bad = self.member("bad", discord="d-not-a-snowflake")
        self.add(none, 9)
        rows = self.by_org_user(self.all_pages())
        for ou in (none, empty, bad):
            with self.subTest(member=ou.user.username):
                self.assertEqual(
                    rows[str(ou.pk)],
                    {
                        "user_id": str(ou.user_id),
                        "org_user_id": str(ou.pk),
                        "discord_id": None,
                        "status": "unavailable",
                        "reason": "discord_mapping_missing",
                    },
                )

    def test_other_org_members_and_rows_excluded(self) -> None:
        mine = self.member("mine")
        theirs = self.member("theirs", org=self.other_org)
        self.add(theirs, 50)
        rows = self.by_org_user(self.all_pages())
        self.assertEqual(set(rows), {str(mine.pk)})

    def test_export_writes_nothing(self) -> None:
        self.member("ro")
        before = (
            ContributionEntry.objects.count(),
            OrgUser.objects.count(),
            CustomUser.objects.count(),
        )
        self.all_pages(limit=1)
        self.assertEqual(
            (
                ContributionEntry.objects.count(),
                OrgUser.objects.count(),
                CustomUser.objects.count(),
            ),
            before,
        )


class FormatPointsTests(TestCase):
    def test_signed_int64_decimal_strings(self) -> None:
        self.assertEqual(format_points(0), "0")
        self.assertEqual(format_points(-0), "0")
        self.assertEqual(format_points(-4), "-4")
        self.assertEqual(format_points(18), "18")
        self.assertEqual(format_points(INT64_MAX), str(INT64_MAX))
        self.assertEqual(format_points(INT64_MIN), str(INT64_MIN))

    def test_out_of_range_or_non_integer_raises(self) -> None:
        for bad in (INT64_MAX + 1, INT64_MIN - 1, 1.0, True, "1", None):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                format_points(bad)  # type: ignore[arg-type]


class AvailabilityTests(_ContributionsBase):
    def test_query_error_503_not_empty_or_zero(self) -> None:
        self.member("q")
        with patch(
            "org.integration.contributions._totals",
            side_effect=OperationalError("boom"),
        ):
            resp = self.get()
        self.assertError(resp, 503, "ledger_unavailable")
        self.assertNotIn("boom", resp.content.decode())
        self.assertNotIn("members", resp.json())

    def test_membership_query_error_503(self) -> None:
        self.member("m")
        with patch(
            "org.integration.contributions._membership",
            side_effect=OperationalError("boom"),
        ):
            self.assertError(self.get(), 503, "ledger_unavailable")

    def test_out_of_range_total_fails_the_page_not_clamped(self) -> None:
        self.member("huge")
        with patch(
            "org.integration.contributions._totals",
            side_effect=lambda org, pks: dict.fromkeys(pks, INT64_MAX + 1),
        ):
            resp = self.get()
        self.assertError(resp, 500, "internal_error")
        self.assertNotIn(str(INT64_MAX + 1), resp.content.decode())


class PagingTests(_ContributionsBase):
    def setUp(self) -> None:
        super().setUp()
        self.ous = [self.member(f"pg_{i}") for i in range(5)]
        self.ous.append(self.member("pg_nodc", discord=None))

    def test_pages_sorted_by_org_user_no_duplicates_and_limit_bounds(self) -> None:
        full = self.all_pages(limit=100)
        one_by_one = self.all_pages(limit=1)
        self.assertEqual(full, one_by_one)
        ids = [int(r["org_user_id"]) for r in full]
        self.assertEqual(ids, sorted(ou.pk for ou in self.ous))
        self.assertEqual(self.get().json()["members"], full)
        for bad in ("0", "101", "-1", "01", "1.0", "x", ""):
            with self.subTest(limit=bad):
                self.assertError(self.get({"limit": bad}), 400, "invalid_request")

    def test_unknown_or_repeated_query_parameters_rejected(self) -> None:
        self.assertError(self.get({"limit": "1", "q": "x"}), 400, "invalid_request")
        resp = self.bearer().get(self.url() + "?limit=1&limit=2")
        self.assertError(resp, 400, "invalid_request")

    def test_each_page_has_its_own_observation(self) -> None:
        first = self.get({"limit": 2}).json()
        with patch(
            "org.integration.contributions.timezone.now",
            return_value=datetime(2026, 11, 24, 12, 1, tzinfo=UTC),
        ):
            second = self.get({"limit": 2, "cursor": first["next_cursor"]}).json()
        self.assertEqual(second["observed_at"], "2026-11-24T12:01:00.000000Z")
        self.assertNotEqual(first["observed_at"], second["observed_at"])

    def test_pages_bound_to_membership_identity_not_mutable_points(self) -> None:
        first = self.get({"limit": 2}).json()
        cursor = first["next_cursor"]
        self.assertTrue(cursor)
        self.assertLessEqual(len(cursor), 2048)

        # Points move between pages: allowed, this is a live per-page read.
        self.add(self.ous[3], 7)
        self.add(self.ous[0], -2)
        page = self.get({"limit": 2, "cursor": cursor})
        self.assertEqual(page.status_code, 200, page.content)
        self.assertEqual(
            self.by_org_user(page.json()["members"])[str(self.ous[3].pk)]["points"],
            "7",
        )

        # Relinking a member's Discord identity invalidates the cursor.
        user = self.ous[4].user
        user.discordId = "123456789099999999"
        user.save()
        self.assertError(
            self.get({"limit": 2, "cursor": cursor}), 409, "mapping_changed"
        )

        # So does removing a member.
        cursor = self.get({"limit": 2}).json()["next_cursor"]
        self.ous[1].delete()
        self.assertError(
            self.get({"limit": 2, "cursor": cursor}), 409, "mapping_changed"
        )

        # And adding one.
        cursor = self.get({"limit": 2}).json()["next_cursor"]
        self.member("late")
        self.assertError(
            self.get({"limit": 2, "cursor": cursor}), 409, "mapping_changed"
        )

    def test_cursor_bound_to_org_and_resource(self) -> None:
        first = self.get({"limit": 1}).json()
        cursor = first["next_cursor"]
        self.assertError(self.get({"cursor": cursor + "x"}), 400, "invalid_cursor")
        self.assertError(self.get({"cursor": "a" * 2049}), 400, "invalid_cursor")
        self.assertError(self.get({"cursor": ""}), 400, "invalid_cursor")
        current = _fingerprint(_membership(self.org))
        for org_id, resource, key in (
            (self.other_org.pk, "contributions", [self.ous[0].pk]),
            (self.org.pk, "event_recipients:1", [self.ous[0].pk]),
            (self.org.pk, "contributions", [0]),
            (self.org.pk, "contributions", ["1"]),
            (self.org.pk, "contributions", [1, 2]),
        ):
            with self.subTest(org=org_id, resource=resource, key=key):
                forged = encode_cursor(
                    org_id=org_id, resource=resource, key=key, fingerprint=current
                )
                self.assertError(self.get({"cursor": forged}), 400, "invalid_cursor")

    def test_service_matches_view(self) -> None:
        page = list_contribution_totals(self.org, limit=100, cursor=None)
        self.assertEqual(page["members"], self.get().json()["members"])

    def test_query_count_does_not_grow_per_member(self) -> None:
        def count() -> int:
            with CaptureQueriesContext(connection) as ctx:
                self.assertEqual(self.get({"limit": 100}).status_code, 200)
            return len(ctx.captured_queries)

        count()  # the first request of the day creates the token usage row
        baseline = count()
        for i in range(10):
            ou = self.member(f"qc_{i}")
            self.add(ou, i)
        self.assertEqual(count(), baseline)


class AuthorizationTests(_ContributionsBase):
    def setUp(self) -> None:
        super().setUp()
        self.member("auth")

    def test_requires_contributions_read_grant(self) -> None:
        mmr = issue_token(self.org, self.admin, "mmr")
        self.assertError(self.get(raw=mmr.raw), 403, "operation_not_granted")
        set_org_feature(self.org, FeatureKey.PROMOTION, enabled=True, actor=None)
        promo = issue_token(
            self.org,
            self.admin,
            "promo",
            operations=["promotion:read", "promotion:import"],
        )
        self.assertError(self.get(raw=promo.raw), 403, "operation_not_granted")

    def test_contributions_feature_required(self) -> None:
        set_org_feature(self.org, FeatureKey.CONTRIBUTIONS, enabled=False, actor=None)
        self.assertError(self.get(), 403, "feature_locked")

    def test_no_promotion_binding_or_feature_needed(self) -> None:
        set_org_feature(self.org, FeatureKey.PROMOTION, enabled=False, actor=None)
        with override_settings(PROMOTION_SYNC=()):
            self.assertEqual(self.get().status_code, 200)

    def test_wrong_org_is_404(self) -> None:
        self.assertError(self.get(org=self.other_org), 404, "not_found")

    def test_revoked_token_and_demoted_owner_denied(self) -> None:
        self.org.admins.remove(self.admin)
        self.assertError(self.get(), 403, "not_permitted")
        self.org.admins.add(self.admin)
        self.assertEqual(self.get().status_code, 200)
        self.issued.token.revoked_at = timezone.now()
        self.issued.token.save()
        self.assertError(self.get(), 401, "unauthorized")

    def test_session_and_missing_credentials_rejected(self) -> None:
        client = APIClient()
        self.assertError(client.get(self.url()), 401, "unauthorized")
        client.force_authenticate(self.admin)
        self.assertError(client.get(self.url()), 401, "unauthorized")

    def test_only_get_allowed(self) -> None:
        resp = self.bearer().post(self.url(), {}, format="json")
        self.assertError(resp, 405, "method_not_allowed")
