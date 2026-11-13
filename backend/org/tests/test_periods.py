from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from structlog.testing import capture_logs

from app.models import CustomUser, Organization
from org.contributions.periods import (
    Period,
    local_day_start_utc,
    local_noon_utc,
    parse_period,
    resolve_org_tz,
)


class OrgPeriodsTest(TestCase):
    def setUp(self) -> None:
        self.owner = CustomUser.objects.create_user(
            username="periods_owner", password="x"
        )
        self.org = Organization.objects.create(
            name="Periods Org", owner=self.owner, timezone="America/New_York"
        )

    def test_month_range_new_york(self) -> None:
        period = parse_period(self.org, "2026-10")
        self.assertEqual(period.start, datetime(2026, 10, 1, 4, 0, tzinfo=UTC))
        self.assertEqual(period.end, datetime(2026, 11, 1, 4, 0, tzinfo=UTC))
        self.assertEqual(period.label, "2026-10")

    def test_december_rolls_into_next_year(self) -> None:
        period = parse_period(self.org, "2026-12")
        self.assertEqual(period.start, datetime(2026, 12, 1, 5, 0, tzinfo=UTC))
        self.assertEqual(period.end, datetime(2027, 1, 1, 5, 0, tzinfo=UTC))

    def test_all_time(self) -> None:
        for value in (None, "all"):
            period = parse_period(self.org, value)
            self.assertEqual(period, Period(start=None, end=None, label="all"))

    def test_oct31_11pm_eastern_in_october(self) -> None:
        moment = datetime(
            2026, 10, 31, 23, 0, tzinfo=ZoneInfo("America/New_York")
        ).astimezone(UTC)
        october = parse_period(self.org, "2026-10")
        november = parse_period(self.org, "2026-11")
        assert october.start and october.end and november.start and november.end
        self.assertTrue(october.start <= moment < october.end)
        self.assertFalse(november.start <= moment < november.end)

    def test_local_noon_utc_nov1_ny(self) -> None:
        self.assertEqual(
            local_noon_utc(self.org, date(2026, 11, 1)),
            datetime(2026, 11, 1, 17, 0, tzinfo=UTC),
        )

    def test_local_day_start_utc_ny(self) -> None:
        self.assertEqual(
            local_day_start_utc(self.org, date(2026, 11, 1)),
            datetime(2026, 11, 1, 4, 0, tzinfo=UTC),
        )

    def test_bad_timezone_falls_back_to_utc(self) -> None:
        Organization.objects.filter(pk=self.org.pk).update(timezone="Mars/Base")
        self.org.refresh_from_db()
        with capture_logs() as logs:
            self.assertEqual(resolve_org_tz(self.org), ZoneInfo("UTC"))
        warnings = [e for e in logs if e["event"] == "org_timezone_invalid"]
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["log_level"], "warning")
        self.assertEqual(warnings[0]["system"], "org")
        self.assertEqual(warnings[0]["subsystem"], "contributions")
        period = parse_period(self.org, "2026-10")
        self.assertEqual(period.start, datetime(2026, 10, 1, tzinfo=UTC))
        self.assertEqual(period.end, datetime(2026, 11, 1, tzinfo=UTC))
        self.assertEqual(
            local_noon_utc(self.org, date(2026, 11, 1)),
            datetime(2026, 11, 1, 12, 0, tzinfo=UTC),
        )

    def test_blank_timezone_falls_back_to_utc(self) -> None:
        Organization.objects.filter(pk=self.org.pk).update(timezone="")
        self.org.refresh_from_db()
        self.assertEqual(resolve_org_tz(self.org), ZoneInfo("UTC"))

    def test_parse_period_rejects_garbage(self) -> None:
        for value in ("garbage", "2026-13", "2026-1", "2026-00", "26-10", ""):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_period(self.org, value)


class OrganizationTimezoneValidatorTest(TestCase):
    def setUp(self) -> None:
        self.owner = CustomUser.objects.create_user(username="tz_owner", password="x")
        self.org = Organization.objects.create(name="TZ Org", owner=self.owner)
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner)
        self.url = f"/api/organizations/{self.org.pk}/"

    def test_org_patch_rejects_bad_timezone(self) -> None:
        resp = self.client.patch(self.url, {"timezone": "Mars/Base"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("timezone", resp.data)
        self.org.refresh_from_db()
        self.assertEqual(self.org.timezone, "America/New_York")

    def test_org_patch_accepts_valid_timezone(self) -> None:
        resp = self.client.patch(self.url, {"timezone": "Europe/Berlin"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.org.refresh_from_db()
        self.assertEqual(self.org.timezone, "Europe/Berlin")
