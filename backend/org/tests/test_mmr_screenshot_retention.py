from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest import mock

from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

import app.internal_client as internal_client
from app.models import CustomUser
from league.models import League, LeagueUser
from lobby.tests.test_beat_schedule import beat_schedule
from org.mmr_requests.retention import purge_expired_screenshots
from org.models import MmrChangeRequest, Organization, OrgUser
from org.tasks import purge_expired_mmr_screenshots
from org.tests.mmr_request_mixin import MmrRequestTestMixin

Status = MmrChangeRequest.Status
TOKEN = "test-internal-token"
PURGE_URL = "/api/internal/mmr-requests/purge-screenshots/"


class RetentionBase(MmrRequestTestMixin, APITestCase):
    def setUp(self) -> None:
        super().setUp()
        self.org = Organization.objects.create(name="MMR Retention Org")
        self.league = League.objects.create(
            name="MMR Retention League", organization=self.org
        )
        self.member = CustomUser.objects.create(username="mmrret_member")
        self.staff = CustomUser.objects.create(username="mmrret_staff")
        self.org.staff.add(self.staff)
        self.ou = OrgUser.objects.create(user=self.member, organization=self.org)
        self.lu = LeagueUser.objects.create(
            user=self.member, org_user=self.ou, league=self.league
        )
        self.client.force_login(self.member)

    def decided(self, status: str, days_ago: float, **kwargs: Any) -> MmrChangeRequest:
        return self.make_request(
            org_user=self.ou,
            status=status,
            reviewed_at=timezone.now() - timedelta(days=days_ago),
            reviewed_by=self.staff,
            **kwargs,
        )

    def purge(self, **kwargs: Any) -> int:
        with self.captureOnCommitCallbacks(execute=True):
            return purge_expired_screenshots(**kwargs).purged

    def file_path(self, row: MmrChangeRequest) -> Path:
        return Path(self.media_root) / row.screenshot.name

    def assert_purged(self, row: MmrChangeRequest, path: Path) -> None:
        row.refresh_from_db()
        self.assertEqual(row.screenshot.name, "")
        self.assertEqual(row.screenshot_content_type, "")
        self.assertIsNotNone(row.screenshot_purged_at)
        self.assertFalse(path.exists())

    def assert_kept(self, row: MmrChangeRequest, path: Path) -> None:
        row.refresh_from_db()
        self.assertNotEqual(row.screenshot.name, "")
        self.assertIsNone(row.screenshot_purged_at)
        self.assertTrue(path.exists())


class PurgeTests(RetentionBase):
    def test_old_decided_requests_purged_and_audit_row_kept(self) -> None:
        rows = [
            self.decided(Status.APPROVED, 8, approved_mmr=4000),
            self.decided(Status.REJECTED, 8, rejection_reason="blurry"),
            self.decided(Status.SUPERSEDED, 30, approved_mmr=4200),
        ]
        paths = [self.file_path(r) for r in rows]
        self.assertEqual(self.purge(), 3)
        for row, path in zip(rows, paths):
            with self.subTest(status=row.status):
                self.assert_purged(row, path)
        self.assertEqual(MmrChangeRequest.objects.count(), 3)
        rejected = MmrChangeRequest.objects.get(status=Status.REJECTED)
        self.assertEqual(rejected.rejection_reason, "blurry")
        self.assertEqual(self.media_files(), [])

    def test_recent_decided_requests_kept(self) -> None:
        row = self.decided(Status.APPROVED, 6)
        path = self.file_path(row)
        self.assertEqual(self.purge(), 0)
        self.assert_kept(row, path)

    def test_pending_never_touched(self) -> None:
        row = self.make_request(
            org_user=self.ou, reviewed_at=timezone.now() - timedelta(days=60)
        )
        path = self.file_path(row)
        self.assertEqual(self.purge(), 0)
        self.assert_kept(row, path)

    def test_league_and_staff_set_rows_purged(self) -> None:
        league_row = self.decided(Status.APPROVED, 10, league_user=self.lu)
        staff_row = self.decided(
            Status.APPROVED, 10, source=MmrChangeRequest.Source.STAFF, game_type=2
        )
        staff_no_file = self.decided(
            Status.APPROVED,
            10,
            source=MmrChangeRequest.Source.STAFF,
            with_screenshot=False,
            game_type=3,
        )
        paths = [self.file_path(league_row), self.file_path(staff_row)]
        self.assertEqual(self.purge(), 2)
        self.assert_purged(league_row, paths[0])
        self.assert_purged(staff_row, paths[1])
        staff_no_file.refresh_from_db()
        self.assertIsNone(staff_no_file.screenshot_purged_at)

    def test_missing_file_is_fine(self) -> None:
        row = self.decided(Status.APPROVED, 8)
        path = self.file_path(row)
        path.unlink()
        self.assertEqual(self.purge(), 1)
        self.assert_purged(row, path)

    def test_second_run_is_noop(self) -> None:
        row = self.decided(Status.REJECTED, 8)
        self.assertEqual(self.purge(), 1)
        row.refresh_from_db()
        first = row.screenshot_purged_at
        self.assertEqual(self.purge(), 0)
        row.refresh_from_db()
        self.assertEqual(row.screenshot_purged_at, first)

    def test_batches(self) -> None:
        rows = [self.decided(Status.APPROVED, 8, game_type=g) for g in (1, 2, 3)]
        with self.captureOnCommitCallbacks(execute=True):
            result = purge_expired_screenshots(batch_size=2)
        self.assertEqual((result.purged, result.batches), (3, 2))
        for row in rows:
            row.refresh_from_db()
            self.assertEqual(row.screenshot.name, "")
        self.assertEqual(self.media_files(), [])

    @override_settings(MMR_SCREENSHOT_RETENTION_DAYS=30)
    def test_setting_override(self) -> None:
        old = self.decided(Status.APPROVED, 31)
        recent = self.decided(Status.REJECTED, 8)
        old_path, recent_path = self.file_path(old), self.file_path(recent)
        self.assertEqual(self.purge(), 1)
        self.assert_purged(old, old_path)
        self.assert_kept(recent, recent_path)

    def test_files_kept_when_transaction_rolls_back(self) -> None:
        row = self.decided(Status.APPROVED, 8)
        path = self.file_path(row)
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            purge_expired_screenshots()
        self.assertEqual(len(callbacks), 1)
        self.assertTrue(path.exists())

    def test_purge_logged(self) -> None:
        self.decided(Status.APPROVED, 8)
        with mock.patch("org.mmr_requests.retention.log") as log:
            self.purge()
        log.info.assert_called_once_with(
            "mmr_screenshots_purged",
            system="org",
            subsystem="mmr_requests",
            purged=1,
            batches=1,
            retention_days=7,
        )

    def test_member_row_without_screenshot_still_needs_purge_marker(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.decided(Status.APPROVED, 8, with_screenshot=False)


class PurgedSerializationTests(RetentionBase):
    def test_mine_reports_no_screenshot_after_purge(self) -> None:
        row = self.decided(Status.APPROVED, 8)
        self.purge()
        body = self.client.get(reverse("mmr-request-mine")).json()
        self.assertEqual(len(body), 1)
        self.assertFalse(body[0]["has_screenshot"])
        self.assertIsNone(body[0]["screenshot_url"])
        row.refresh_from_db()
        self.assertEqual(
            datetime.fromisoformat(body[0]["screenshot_purged_at"]),
            row.screenshot_purged_at,
        )

    def test_unpurged_row_has_null_purged_at(self) -> None:
        self.decided(Status.APPROVED, 1)
        body = self.client.get(reverse("mmr-request-mine")).json()
        self.assertTrue(body[0]["has_screenshot"])
        self.assertIsNone(body[0]["screenshot_purged_at"])

    def test_screenshot_endpoint_404_after_purge(self) -> None:
        row = self.decided(Status.REJECTED, 8)
        self.purge()
        self.client.force_login(self.staff)
        url = reverse("mmr-request-screenshot", kwargs={"pk": row.pk})
        self.assertEqual(self.client.get(url).status_code, 404)


@override_settings(INTERNAL_SERVICE_TOKEN=TOKEN)
class InternalPurgeEndpointTests(RetentionBase):
    def test_requires_internal_token(self) -> None:
        self.client.logout()
        self.assertIn(self.client.post(PURGE_URL, {}).status_code, (401, 403))

    def test_purges_and_reports_counts(self) -> None:
        row = self.decided(Status.APPROVED, 8)
        path = self.file_path(row)
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(
                PURGE_URL, {}, format="json", HTTP_X_INTERNAL_TOKEN=TOKEN
            )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json(), {"purged": 1, "batches": 1, "retention_days": 7})
        self.assert_purged(row, path)


class PurgeTaskTests(SimpleTestCase):
    def test_task_calls_internal_api(self) -> None:
        with mock.patch(
            "org.tasks.purge_mmr_screenshots",
            return_value={"purged": 2, "batches": 1, "retention_days": 7},
        ) as call:
            purge_expired_mmr_screenshots()
        call.assert_called_once_with()

    def test_client_posts_to_purge_endpoint(self) -> None:
        response = mock.Mock(ok=True)
        response.json.return_value = {"purged": 0, "batches": 0, "retention_days": 7}
        with mock.patch.object(
            internal_client.transport, "post", return_value=response
        ) as post:
            result = internal_client.purge_mmr_screenshots()
        post.assert_called_once_with("/mmr-requests/purge-screenshots/", {})
        self.assertEqual(result, {"purged": 0, "batches": 0, "retention_days": 7})

    def test_client_returns_none_on_failure(self) -> None:
        with mock.patch.object(internal_client.transport, "post", return_value=None):
            self.assertIsNone(internal_client.purge_mmr_screenshots())

    def test_task_name(self) -> None:
        self.assertEqual(
            purge_expired_mmr_screenshots.name,
            "org.tasks.purge_expired_mmr_screenshots",
        )

    def test_nightly_entry_in_both_schedules(self) -> None:
        for filename in ("celery.py", "celery_light.py"):
            with self.subTest(filename=filename):
                entry = beat_schedule(filename)["purge-mmr-screenshots-nightly"]
                self.assertEqual(
                    entry["task"], "org.tasks.purge_expired_mmr_screenshots"
                )
