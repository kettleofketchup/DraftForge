import json
from io import BytesIO
from typing import Any
from unittest.mock import patch

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http.multipartparser import MultiPartParser
from django.test import override_settings
from django.urls import reverse
from PIL import Image
from rest_framework.test import APIClient, APITestCase

from app.models import CustomUser, GameType
from league.models import League, LeagueUser
from org.mmr import LEAGUE_GAME
from org.mmr_requests.screenshots import MAX_BYTES, SanitizerBusy, StorageFull
from org.mmr_requests.upload_guard import MAX_BODY_BYTES
from org.models import MmrChangeRequest, Organization, OrgUser, OrgUserGameMmr
from org.tests.mmr_request_mixin import MmrRequestTestMixin

DL = GameType.DEADLOCK
PENDING = MmrChangeRequest.Status.PENDING
CREATE_URL = "/api/mmr-requests/"
CSRF_TOKEN = "a" * 32


class MmrRequestApiBase(MmrRequestTestMixin, APITestCase):
    def setUp(self) -> None:
        super().setUp()
        self.org = Organization.objects.create(name="MMR API Org")
        self.league = League.objects.create(
            name="MMR API League", organization=self.org
        )
        self.member = CustomUser.objects.create(username="mmrapi_member")
        self.other = CustomUser.objects.create(username="mmrapi_other")
        self.staff = CustomUser.objects.create(username="mmrapi_staff")
        self.org.staff.add(self.staff)
        self.ou = OrgUser.objects.create(user=self.member, organization=self.org)
        self.other_ou = OrgUser.objects.create(user=self.other, organization=self.org)
        self.lu = LeagueUser.objects.create(
            user=self.member, org_user=self.ou, league=self.league, mmr=3100
        )
        self.other_lu = LeagueUser.objects.create(
            user=self.other, org_user=self.other_ou, league=self.league
        )
        self.client.force_login(self.member)

    def org_payload(self, **overrides: Any) -> dict[str, Any]:
        data: dict[str, Any] = {
            "target": "org",
            "org_user": self.ou.pk,
            "game_type": int(GameType.DOTA2),
            "requested_mmr": 4500,
            "screenshot": self.png_upload(),
            "note": "new peak",
        }
        data.update(overrides)
        return data

    def league_payload(self, **overrides: Any) -> dict[str, Any]:
        data: dict[str, Any] = {
            "target": "league",
            "league_user": self.lu.pk,
            "requested_mmr": 4700,
            "screenshot": self.png_upload(),
        }
        data.update(overrides)
        return data

    def post_create(
        self, data: dict[str, Any], client: APIClient | None = None, **extra: Any
    ) -> Any:
        return (client or self.client).post(
            CREATE_URL, data, format="multipart", **extra
        )

    def csrf_client(self, user: CustomUser) -> APIClient:
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(user)
        client.cookies[settings.CSRF_COOKIE_NAME] = CSRF_TOKEN
        return client


class CreateTests(MmrRequestApiBase):
    def test_create_org_request_201(self) -> None:
        OrgUserGameMmr.objects.create(
            org_user=self.ou, game_type=GameType.DOTA2, mmr=3000
        )
        resp = self.post_create(self.org_payload())
        self.assertEqual(resp.status_code, 201, resp.content)
        row = MmrChangeRequest.objects.get()
        self.assertEqual(row.status, PENDING)
        self.assertEqual(row.target, "org")
        self.assertEqual(row.previous_mmr, 3000)
        self.assertFalse(row.previous_verified)
        self.assertEqual(row.requester, self.member)
        self.assertEqual(row.subject_user, self.member)
        self.assertEqual(row.note, "new peak")
        self.assertEqual(row.screenshot_content_type, "image/png")
        self.assertEqual(len(self.media_files()), 1)
        self.assertNotIn("mmr_requests/", resp.content.decode())
        body = resp.json()
        self.assertEqual(body["id"], row.pk)
        self.assertEqual(body["current_mmr"], 3000)
        self.assertTrue(body["has_screenshot"])
        self.assertEqual(
            body["screenshot_url"], f"/api/mmr-requests/{row.pk}/screenshot/"
        )
        self.assertEqual(
            body["organization"], {"pk": self.org.pk, "name": self.org.name}
        )
        self.assertIsNone(body["league"])
        self.assertFalse(body["can_review"])

    def test_create_snapshots_verified_value(self) -> None:
        OrgUserGameMmr.objects.create(
            org_user=self.ou,
            game_type=DL,
            mmr=1500,
            verified_by=self.staff,
            verified_at="2026-11-01T00:00:00Z",
        )
        resp = self.post_create(self.org_payload(game_type=int(DL), requested_mmr=1800))
        self.assertEqual(resp.status_code, 201, resp.content)
        row = MmrChangeRequest.objects.get()
        self.assertEqual((row.previous_mmr, row.previous_verified), (1500, True))

    def test_create_league_request_forces_league_game(self) -> None:
        resp = self.post_create(self.league_payload(game_type=int(DL)))
        self.assertEqual(resp.status_code, 201, resp.content)
        row = MmrChangeRequest.objects.get()
        self.assertEqual(row.target, "league")
        self.assertEqual(row.game_type, LEAGUE_GAME)
        self.assertEqual(row.league_id, self.league.pk)
        self.assertEqual(row.league_user_id, self.lu.pk)
        self.assertEqual(row.org_user_id, self.ou.pk)
        self.assertEqual(row.previous_mmr, 3100)
        self.assertEqual(
            resp.json()["league"], {"pk": self.league.pk, "name": self.league.name}
        )

    def test_create_other_members_org_user_403(self) -> None:
        resp = self.post_create(self.org_payload(org_user=self.other_ou.pk))
        self.assertEqual(resp.status_code, 403, resp.content)
        self.assertFalse(MmrChangeRequest.objects.exists())
        self.assertEqual(self.media_files(), [])

    def test_create_other_users_league_user_403(self) -> None:
        resp = self.post_create(self.league_payload(league_user=self.other_lu.pk))
        self.assertEqual(resp.status_code, 403, resp.content)
        self.assertFalse(MmrChangeRequest.objects.exists())

    def test_create_unknown_membership_400(self) -> None:
        resp = self.post_create(self.org_payload(org_user=999999))
        self.assertEqual(resp.status_code, 400)
        self.assertIn("org_user", resp.json())

    def test_create_mmr_bounds_400(self) -> None:
        for value in (0, 20001, "abc"):
            with self.subTest(value=value):
                resp = self.post_create(self.org_payload(requested_mmr=value))
                self.assertEqual(resp.status_code, 400, resp.content)
                self.assertIn("requested_mmr", resp.json())
        self.assertFalse(MmrChangeRequest.objects.exists())
        self.assertEqual(self.media_files(), [])

    def test_create_missing_screenshot_400(self) -> None:
        data = self.org_payload()
        del data["screenshot"]
        resp = self.post_create(data)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("screenshot", resp.json())

    def test_create_bad_image_400_code(self) -> None:
        bad = SimpleUploadedFile("s.png", b"<?php echo 1; ?>", content_type="image/png")
        resp = self.post_create(self.org_payload(screenshot=bad))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json(), {"screenshot": ["invalid_image"]})
        self.assertEqual(self.media_files(), [])

    def test_create_unsupported_type_400(self) -> None:
        buf = BytesIO()
        Image.new("RGB", (20, 20)).save(buf, format="GIF")
        gif = SimpleUploadedFile("s.png", buf.getvalue(), content_type="image/png")
        resp = self.post_create(self.org_payload(screenshot=gif))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json(), {"screenshot": ["unsupported_type"]})

    def test_create_league_of_other_org_400(self) -> None:
        other_org = Organization.objects.create(name="MMR API Other Org")
        foreign = League.objects.create(name="Foreign League", organization=other_org)
        lu = LeagueUser.objects.create(
            user=self.member, org_user=self.ou, league=foreign
        )
        resp = self.post_create(self.league_payload(league_user=lu.pk))
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("league_user", resp.json())
        self.assertFalse(MmrChangeRequest.objects.exists())
        self.assertEqual(self.media_files(), [])

    def test_create_orgless_league_201(self) -> None:
        orgless = League.objects.create(name="Orgless League", organization=None)
        lu = LeagueUser.objects.create(
            user=self.member, org_user=self.ou, league=orgless
        )
        resp = self.post_create(self.league_payload(league_user=lu.pk))
        self.assertEqual(resp.status_code, 201, resp.content)
        row = MmrChangeRequest.objects.get()
        self.assertEqual(row.league_id, orgless.pk)
        self.assertEqual(row.organization_id, self.org.pk)

    def test_create_duplicate_pending_409_no_file(self) -> None:
        existing = self.make_request(org_user=self.ou, game_type=GameType.DOTA2)
        before = self.media_files()
        resp = self.post_create(self.org_payload())
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(
            resp.json(), {"error": "pending_exists", "request_id": existing.pk}
        )
        self.assertEqual(self.media_files(), before)

    def test_create_integrity_error_409_no_file(self) -> None:
        existing = self.make_request(org_user=self.ou, game_type=GameType.DOTA2)
        before = self.media_files()
        with patch(
            "org.mmr_requests.services.find_pending_request_id", return_value=None
        ):
            resp = self.post_create(self.org_payload())
        self.assertEqual(resp.status_code, 409, resp.content)
        self.assertEqual(
            resp.json(), {"error": "pending_exists", "request_id": existing.pk}
        )
        self.assertEqual(self.media_files(), before)
        self.assertEqual(MmrChangeRequest.objects.count(), 1)

    def test_create_integrity_error_409_media_empty(self) -> None:
        OrgUserGameMmr.objects.create(
            org_user=self.ou, game_type=GameType.DOTA2, mmr=10
        )
        MmrChangeRequest.objects.create(
            requester=self.member,
            subject_user=self.member,
            organization=self.org,
            org_user=self.ou,
            target="org",
            game_type=GameType.DOTA2,
            requested_mmr=100,
            previous_mmr=10,
            screenshot="mmr_requests/x/y.png",
        )
        with patch(
            "org.mmr_requests.services.find_pending_request_id", return_value=None
        ):
            resp = self.post_create(self.org_payload())
        self.assertEqual(resp.status_code, 409, resp.content)
        self.assertEqual(self.media_files(), [])

    def test_create_anonymous_403(self) -> None:
        self.client.logout()
        resp = self.post_create(self.org_payload())
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(MmrChangeRequest.objects.exists())

    def test_create_9mb_body_413_before_parse(self) -> None:
        client = self.csrf_client(self.member)
        big = SimpleUploadedFile(
            "s.png", b"\0" * MAX_BODY_BYTES, content_type="image/png"
        )
        with patch.object(MultiPartParser, "parse", autospec=True) as parse:
            resp = self.post_create(
                self.org_payload(screenshot=big),
                client=client,
                HTTP_X_CSRFTOKEN=CSRF_TOKEN,
            )
        self.assertEqual(resp.status_code, 413)
        self.assertEqual(json.loads(resp.content), {"error": "too_large"})
        parse.assert_not_called()
        self.assertFalse(MmrChangeRequest.objects.exists())

    def test_create_file_part_over_8mb_under_body_cap(self) -> None:
        size = MAX_BYTES + 512 * 1024
        self.assertLess(size, MAX_BODY_BYTES)
        big = SimpleUploadedFile("s.png", b"\0" * size, content_type="image/png")
        resp = self.post_create(self.org_payload(screenshot=big))
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual(resp.json(), {"screenshot": ["too_large"]})
        self.assertEqual(self.media_files(), [])

    def test_create_busy_503(self) -> None:
        with patch(
            "org.mmr_requests.services.sanitize_screenshot", side_effect=SanitizerBusy
        ):
            resp = self.post_create(self.org_payload())
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json(), {"error": "busy"})
        self.assertFalse(MmrChangeRequest.objects.exists())
        self.assertEqual(self.media_files(), [])

    def test_create_note_501_400(self) -> None:
        resp = self.post_create(self.org_payload(note="x" * 501))
        self.assertEqual(resp.status_code, 400)
        self.assertIn("note", resp.json())
        resp = self.post_create(self.org_payload(note="x" * 500))
        self.assertEqual(resp.status_code, 201, resp.content)

    def test_create_storage_full_507(self) -> None:
        with patch(
            "org.mmr_requests.services.sanitize_screenshot", side_effect=StorageFull
        ):
            resp = self.post_create(self.org_payload())
        self.assertEqual(resp.status_code, 507)
        self.assertEqual(resp.json(), {"error": "storage_full"})
        self.assertFalse(MmrChangeRequest.objects.exists())

    @override_settings(MMR_THROTTLE_IN_TESTS=True)
    def test_create_throttled_429_on_11th(self) -> None:
        for _ in range(10):
            resp = self.post_create({"target": "org"})
            self.assertEqual(resp.status_code, 400)
        resp = self.post_create(self.org_payload())
        self.assertEqual(resp.status_code, 429)
        self.assertFalse(MmrChangeRequest.objects.exists())

    def test_create_csrf_enforced(self) -> None:
        client = self.csrf_client(self.member)
        resp = self.post_create(self.org_payload(), client=client)
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(MmrChangeRequest.objects.exists())
        resp = self.post_create(
            self.org_payload(), client=client, HTTP_X_CSRFTOKEN=CSRF_TOKEN
        )
        self.assertEqual(resp.status_code, 201, resp.content)


class MineTests(MmrRequestApiBase):
    def test_mine_lists_only_subject_rows(self) -> None:
        mine = self.make_request(org_user=self.ou)
        mine_league = self.make_request(org_user=self.ou, league_user=self.lu)
        self.make_request(org_user=self.other_ou)
        resp = self.client.get(reverse("mmr-request-mine"))
        self.assertEqual(resp.status_code, 200)
        ids = {row["id"] for row in resp.json()}
        self.assertEqual(ids, {mine.pk, mine_league.pk})
        self.assertNotIn("mmr_requests/", resp.content.decode())

    def test_mine_anonymous_403(self) -> None:
        self.client.logout()
        self.assertEqual(self.client.get(reverse("mmr-request-mine")).status_code, 403)


class CancelTests(MmrRequestApiBase):
    def cancel(self, pk: int) -> Any:
        return self.client.post(reverse("mmr-request-cancel", kwargs={"pk": pk}))

    def test_cancel_by_subject_clears_file_on_commit(self) -> None:
        req = self.make_request(org_user=self.ou)
        self.assertEqual(len(self.media_files()), 1)
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.cancel(req.pk)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["status"], "cancelled")
        self.assertFalse(resp.json()["has_screenshot"])
        req.refresh_from_db()
        self.assertEqual(req.status, MmrChangeRequest.Status.CANCELLED)
        self.assertEqual(req.screenshot.name, "")
        self.assertEqual(self.media_files(), [])

    def test_cancel_by_other_403(self) -> None:
        req = self.make_request(org_user=self.other_ou)
        resp = self.cancel(req.pk)
        self.assertEqual(resp.status_code, 403)
        req.refresh_from_db()
        self.assertEqual(req.status, PENDING)

    def test_cancel_not_pending_409(self) -> None:
        req = self.make_request(
            org_user=self.ou, status=MmrChangeRequest.Status.REJECTED
        )
        resp = self.cancel(req.pk)
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json(), {"error": "not_pending", "status": "rejected"})

    def test_cancel_staff_source_403(self) -> None:
        req = self.make_request(
            org_user=self.ou,
            requester=self.staff,
            source=MmrChangeRequest.Source.STAFF,
            status=MmrChangeRequest.Status.APPROVED,
            with_screenshot=False,
        )
        self.assertEqual(self.cancel(req.pk).status_code, 403)

    def test_cancel_missing_404(self) -> None:
        self.assertEqual(self.cancel(999999).status_code, 404)


class ScreenshotTests(MmrRequestApiBase):
    def fetch(self, pk: int) -> Any:
        return self.client.get(reverse("mmr-request-screenshot", kwargs={"pk": pk}))

    def test_screenshot_subject_200_headers(self) -> None:
        req = self.make_request(org_user=self.ou)
        resp = self.fetch(req.pk)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "image/png")
        self.assertEqual(resp["X-Content-Type-Options"], "nosniff")
        self.assertEqual(resp["Cache-Control"], "private, no-store")
        self.assertEqual(
            resp["Content-Security-Policy"],
            "default-src 'none'; img-src 'self'; sandbox",
        )
        self.assertEqual(resp["Cross-Origin-Resource-Policy"], "same-origin")
        self.assertEqual(
            resp["Content-Disposition"], f'inline; filename="mmr-{req.pk}.png"'
        )
        body = b"".join(resp.streaming_content)
        self.assertTrue(body.startswith(b"\x89PNG"))

    def test_screenshot_org_staff_200(self) -> None:
        req = self.make_request(org_user=self.ou)
        self.client.force_login(self.staff)
        resp = self.fetch(req.pk)
        self.assertEqual(resp.status_code, 200)
        b"".join(resp.streaming_content)

    def test_screenshot_other_member_404(self) -> None:
        req = self.make_request(org_user=self.ou)
        self.client.force_login(self.other)
        self.assertEqual(self.fetch(req.pk).status_code, 404)

    def test_screenshot_anon_403(self) -> None:
        req = self.make_request(org_user=self.ou)
        self.client.logout()
        self.assertEqual(self.fetch(req.pk).status_code, 403)

    def test_screenshot_cancelled_404(self) -> None:
        req = self.make_request(org_user=self.ou)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("mmr-request-cancel", kwargs={"pk": req.pk}))
        self.assertEqual(self.fetch(req.pk).status_code, 404)

    def test_screenshot_file_missing_404(self) -> None:
        req = self.make_request(org_user=self.ou)
        for path in self.media_files():
            path.unlink()
        self.assertEqual(self.fetch(req.pk).status_code, 404)
