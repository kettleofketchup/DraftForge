import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path
from unittest import TestCase as PlainTestCase
from unittest.mock import patch

from django.test import TransactionTestCase
from django.urls import reverse
from rest_framework.response import Response
from rest_framework.test import APIClient

from app import export_steam_verification_schema
from app.models import CustomUser
from app.steam_accounts import mark_steam_account_verified
from app.steam_verification_schemas import SteamVerificationOut
from app.user_cache import serialize_user_core
from events.models import Event, EventSignup
from events.services import process_rsvp, staff_add_signup
from events.tests.actors import SYSTEM
from events.tests.base import EventTestCase
from org.membership import resolve_or_create_org_user
from org.models import Organization
from tournament.models import Tournament
from user.tests.test_cacheops_integration import _redis_reachable

SCRIPT = Path(export_steam_verification_schema.__file__)


def _url(pk: int) -> str:
    return reverse("user_steam_verification", kwargs={"pk": pk})


class SteamVerificationEndpointTests(EventTestCase):
    def setUp(self) -> None:
        self.target = self.make_user()
        self.target.steam_account_id = 4242
        self.target.save()
        self.open_event: Event = self.make_event(tournament_league=self.league)
        self.client = APIClient()

    def _self_signup(self) -> EventSignup:
        signup = process_rsvp(self.open_event, self.target, actor=SYSTEM)
        self.assertTrue(signup.self_made)
        return signup

    def _superuser(self) -> CustomUser:
        return CustomUser.objects.create_superuser(
            username="sve_super", password="x", email="sve_super@example.com"
        )

    def _site_staff(self) -> CustomUser:
        staff = CustomUser.objects.create_user(username="sve_staff", password="x")
        staff.is_staff = True
        staff.save()
        return staff

    def _post(
        self,
        actor: CustomUser | None,
        *,
        verified: bool = True,
        steam_account_id: int | None = 4242,
        target: CustomUser | None = None,
    ) -> Response:
        if actor is not None:
            self.client.force_authenticate(actor)
        body: dict[str, object] = {"verified": verified}
        if steam_account_id is not None:
            body["steam_account_id"] = steam_account_id
        return self.client.post(_url((target or self.target).pk), body, format="json")

    def _get(self, actor: CustomUser, target: CustomUser | None = None) -> Response:
        self.client.force_authenticate(actor)
        return self.client.get(_url((target or self.target).pk))

    def _reload(self) -> CustomUser:
        return CustomUser.objects.nocache().get(pk=self.target.pk)

    def assertVerified(self, org_id: int | None, by: CustomUser) -> None:
        user = self._reload()
        self.assertIsNotNone(user.steam_account_verified_at)
        self.assertEqual(user.steam_account_verified_by_id, by.pk)
        self.assertEqual(user.steam_account_verified_org_id, org_id)

    def assertUnverified(self) -> None:
        user = self._reload()
        self.assertIsNone(user.steam_account_verified_at)
        self.assertIsNone(user.steam_account_verified_by_id)
        self.assertIsNone(user.steam_account_verified_org_id)

    def test_post_superuser_other_org_none(self) -> None:
        su = self._superuser()
        resp = self._post(su)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertTrue(resp.json()["steam_account_verified"])
        self.assertIsNone(resp.json()["steam_account_verified_org_name"])
        self.assertVerified(None, su)

    def test_post_self_403(self) -> None:
        su = self._superuser()
        su.steam_account_id = 5151
        su.save()
        resp = self._post(su, steam_account_id=5151, target=su)
        self.assertEqual(resp.status_code, 403)
        su.refresh_from_db()
        self.assertIsNone(su.steam_account_verified_at)

    def test_post_self_as_event_staff_403(self) -> None:
        self.admin.steam_account_id = 6161
        self.admin.save()
        process_rsvp(self.open_event, self.admin, actor=SYSTEM)
        resp = self._post(self.admin, steam_account_id=6161, target=self.admin)
        self.assertEqual(resp.status_code, 403)

    def test_post_site_staff(self) -> None:
        staff = self._site_staff()
        self.assertEqual(self._post(staff).status_code, 200)
        self.assertVerified(None, staff)

    def test_post_event_staff_records_org(self) -> None:
        self._self_signup()
        resp = self._post(self.admin)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["steam_account_verified_org_name"], self.org.name)
        self.assertVerified(self.org.pk, self.admin)

    def test_post_league_staff(self) -> None:
        self._self_signup()
        self.assertEqual(self._post(self.league_staff).status_code, 200)
        self.assertVerified(self.org.pk, self.league_staff)

    def test_post_org_staff_added_member_403(self) -> None:
        actor = CustomUser.objects.create_user(username="sve_org_owner", password="x")
        own_org = Organization.objects.create(name="SVE Own Org", owner=actor)
        own_org.staff.add(actor)
        resolve_or_create_org_user(self.target, own_org)
        self.assertEqual(self._post(actor).status_code, 403)
        self.assertEqual(self._get(actor).status_code, 403)
        self.assertUnverified()

    def test_post_on_behalf_signup_403(self) -> None:
        signup = staff_add_signup(self.open_event, self.target, actor=SYSTEM)
        self.assertFalse(signup.self_made)
        self.assertEqual(self._post(self.admin).status_code, 403)
        self.assertEqual(self._post(self.league_staff).status_code, 403)
        self.assertUnverified()

    def test_post_unrelated_org_staff_403(self) -> None:
        other = Organization.objects.create(
            name="SVE Unrelated", owner=self.unrelated_user
        )
        other.staff.add(self.unrelated_user)
        self._self_signup()
        self.assertEqual(self._post(self.unrelated_user).status_code, 403)
        self.assertUnverified()

    def test_post_plain_member_403(self) -> None:
        self._self_signup()
        self.assertEqual(self._post(self.make_user()).status_code, 403)
        self.assertUnverified()

    def test_anonymous_rejected(self) -> None:
        self._self_signup()
        self.assertIn(self._post(None).status_code, (401, 403))
        self.assertIn(self.client.get(_url(self.target.pk)).status_code, (401, 403))
        self.assertUnverified()

    def test_unknown_pk_404(self) -> None:
        su = self._superuser()
        self.client.force_authenticate(su)
        self.assertEqual(self.client.get(_url(999_999)).status_code, 404)
        resp = self.client.post(
            _url(999_999), {"verified": True, "steam_account_id": 1}, format="json"
        )
        self.assertEqual(resp.status_code, 404)

    def test_post_no_id_400(self) -> None:
        self.target.steam_account_id = None
        self.target.save()
        resp = self._post(self._superuser(), steam_account_id=4242)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(
            resp.json(),
            {"error": "User has no Friend ID", "code": "no_steam_account_id"},
        )

    def test_post_id_changed_409(self) -> None:
        resp = self._post(self._superuser(), steam_account_id=1111)
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(
            resp.json(),
            {
                "error": "The Friend ID changed since you loaded it",
                "code": "id_changed",
                "steam_account_id": 4242,
            },
        )
        self.assertUnverified()

    def test_post_unverify_id_changed_409(self) -> None:
        su = self._superuser()
        self._post(su)
        resp = self._post(su, verified=False, steam_account_id=1111)
        self.assertEqual(resp.status_code, 409)
        self.assertVerified(None, su)

    def test_post_invalid_body_400(self) -> None:
        su = self._superuser()
        resp = self._post(su, steam_account_id=None)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.json())
        self.assertIn("detail", resp.json())
        self.client.force_authenticate(su)
        resp = self.client.post(
            _url(self.target.pk),
            {"verified": True, "steam_account_id": 4242, "extra": 1},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertUnverified()

    def test_post_invalid_body_from_unauthorized_is_403(self) -> None:
        resp = self._post(self.make_user(), steam_account_id=None)
        self.assertEqual(resp.status_code, 403)

    def test_post_idempotent(self) -> None:
        self._self_signup()
        first = self._post(self.admin)
        self.assertEqual(first.status_code, 200)
        before = self._reload()
        second = self._post(self._superuser())
        self.assertEqual(second.status_code, 200)
        after = self._reload()
        self.assertEqual(
            after.steam_account_verified_at, before.steam_account_verified_at
        )
        self.assertEqual(after.steam_account_verified_by_id, self.admin.pk)
        self.assertEqual(after.steam_account_verified_org_id, self.org.pk)
        self.assertEqual(
            second.json()["steam_account_verified_at"],
            first.json()["steam_account_verified_at"],
        )
        self.assertEqual(
            second.json()["steam_account_verified_org_name"], self.org.name
        )

    def test_post_unverify(self) -> None:
        su = self._superuser()
        self._post(su)
        resp = self._post(su, verified=False)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["steam_account_verified"])
        self.assertIsNone(resp.json()["steam_account_verified_at"])
        self.assertUnverified()
        again = self._post(su, verified=False)
        self.assertEqual(again.status_code, 200)
        self.assertUnverified()

    def test_get_can_verify_matches_post(self) -> None:
        self._self_signup()
        staff = self._site_staff()
        cases: list[tuple[CustomUser, int, bool | None]] = [
            (self.admin, 200, True),
            (self.league_staff, 200, True),
            (staff, 200, True),
            (self.make_user(), 403, None),
            (self.target, 403, None),
        ]
        for actor, get_status, can_verify in cases:
            with self.subTest(actor=actor.username):
                resp = self._get(actor)
                self.assertEqual(resp.status_code, get_status)
                if can_verify is not None:
                    self.assertIs(resp.json()["can_verify"], can_verify)
                    post = self._post(actor)
                    self.assertEqual(post.status_code == 200, can_verify)

    def test_get_site_staff_viewing_self_cannot_verify(self) -> None:
        staff = self._site_staff()
        staff.steam_account_id = 7171
        staff.save()
        resp = self._get(staff, target=staff)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["can_verify"])

    def test_get_urls(self) -> None:
        resp = self._get(self._superuser())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(
            body["steam_profile_url"],
            "https://steamcommunity.com/profiles/"
            f"{4242 + CustomUser.STEAM_ID_64_BASE}",
        )
        self.assertEqual(body["dotabuff_url"], "https://www.dotabuff.com/players/4242")
        self.assertEqual(body["steam_account_id"], 4242)
        self.assertFalse(body["steam_account_verified"])

    def test_get_no_id_urls_none(self) -> None:
        self.target.steam_account_id = None
        self.target.save()
        body = self._get(self._superuser()).json()
        self.assertIsNone(body["steam_account_id"])
        self.assertIsNone(body["steam_profile_url"])
        self.assertIsNone(body["dotabuff_url"])

    def test_response_validates_against_pydantic(self) -> None:
        self._self_signup()
        resp = self._post(self.admin)
        model = SteamVerificationOut.model_validate(resp.json())
        self.assertTrue(model.steam_account_verified)
        self.assertIsNotNone(model.steam_account_verified_at)
        self.assertEqual(set(resp.json()), set(SteamVerificationOut.model_fields))
        SteamVerificationOut.model_validate(self._get(self.admin).json())

    def test_verify_logs_actor(self) -> None:
        su = self._superuser()
        with patch("app.steam_accounts.log") as log:
            self._post(su)
            self._post(su, verified=False)
        events = [c.kwargs for c in log.info.call_args_list]
        self.assertEqual([e["verified"] for e in events], [True, False])
        self.assertTrue(all(e["actor_id"] == su.pk for e in events))


class SteamVerificationCacheTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._redis_ok = _redis_reachable()

    def setUp(self) -> None:
        if not self._redis_ok:
            self.skipTest("Cacheops Redis not reachable")
        self.su = CustomUser.objects.create_superuser(
            username="svc_super", password="x", email="svc_super@example.com"
        )
        self.target = CustomUser.objects.create_user(username="svc_target")
        self.target.steam_account_id = 9393
        self.target.save()
        self.tournament = Tournament.objects.create(
            name="SVC Cup", date_played=date.today()
        )
        self.tournament.users.add(self.target)
        self.client = APIClient()
        self.client.force_authenticate(self.su)

    def _detail_user(self) -> dict:
        resp = self.client.get(f"/api/tournaments/{self.tournament.pk}/")
        self.assertEqual(resp.status_code, 200)
        return resp.data["_users"][self.target.pk]

    def test_cache_invalidation_after_verify(self) -> None:
        self.assertFalse(serialize_user_core(self.target.pk)["steam_account_verified"])
        self.assertFalse(self._detail_user()["steam_account_verified"])

        resp = self.client.post(
            _url(self.target.pk),
            {"verified": True, "steam_account_id": 9393},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)

        self.assertTrue(serialize_user_core(self.target.pk)["steam_account_verified"])
        self.assertTrue(self._detail_user()["steam_account_verified"])

        resp = self.client.post(
            _url(self.target.pk),
            {"verified": False, "steam_account_id": 9393},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(serialize_user_core(self.target.pk)["steam_account_verified"])
        self.assertFalse(self._detail_user()["steam_account_verified"])

    def test_get_reads_fresh_after_helper_verify(self) -> None:
        url = _url(self.target.pk)
        self.assertFalse(self.client.get(url).json()["steam_account_verified"])
        mark_steam_account_verified(self.target, self.su, org_id=None)
        self.assertTrue(self.client.get(url).json()["steam_account_verified"])


def _clean_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k != "DJANGO_SETTINGS_MODULE"}


class ExporterTest(PlainTestCase):
    def test_bundle_shape(self) -> None:
        b = export_steam_verification_schema.bundle()
        self.assertEqual(b["source"], "backend/app/steam_verification_schemas.py")
        self.assertEqual(b["regen"], "just py::gen-steam-verification")
        self.assertEqual(b["schema"]["title"], "SteamVerificationApi")
        self.assertLessEqual(
            {"SteamVerificationOut", "SteamVerificationIn"}, set(b["schema"]["$defs"])
        )
        self.assertNotIn("data", b)
        out = b["schema"]["$defs"]["SteamVerificationOut"]
        self.assertEqual(set(out["required"]), set(out["properties"]))
        self.assertNotEqual(out.get("additionalProperties"), False)
        self.assertIs(
            b["schema"]["$defs"]["SteamVerificationIn"]["additionalProperties"], False
        )

    def test_script_runs_isolated(self) -> None:
        result = subprocess.run(
            [sys.executable, "-I", str(SCRIPT)],
            env=_clean_env(),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout), export_steam_verification_schema.bundle()
        )
