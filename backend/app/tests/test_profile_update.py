from unittest.mock import patch

from django.core.cache import cache
from django.db import connection
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient, APITestCase

from app.models import CustomUser, PositionsModel
from app.steam_accounts import mark_steam_account_verified
from steam.services.account_lookup import SteamLookupRateLimited, cached_exists_key

URL = "/api/profile_update"
ENSURE = "events.eligibility.steam.ensure_steam_account_exists"
LOOKUP_ON = override_settings(
    STEAM_ACCOUNT_LOOKUP_ENABLED=True,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)


def _make_profile_user(
    username: str, steam_account_id: int | None = None
) -> CustomUser:
    return CustomUser.objects.create(
        username=username,
        positions=PositionsModel.objects.create(),
        steam_account_id=steam_account_id,
    )


@LOOKUP_ON
class ProfileUpdateFriendIdTests(APITestCase):
    def setUp(self) -> None:
        cache.clear()
        self.user = _make_profile_user("pu-user")
        self.staff = _make_profile_user("pu-staff")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _post(self, steam_account_id: object) -> object:
        return self.client.post(
            URL, {"steam_account_id": steam_account_id}, format="json"
        )

    def _reload(self) -> CustomUser:
        return CustomUser.objects.get(pk=self.user.pk)

    def test_not_found_400_with_code(self) -> None:
        with patch(ENSURE, return_value=False):
            resp = self._post(424242)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["code"], "steam_account_not_found")
        self.assertIn("424242", resp.data["error"])
        self.assertIsNone(self._reload().steam_account_id)

    def test_out_of_range_400(self) -> None:
        with patch(ENSURE) as ensure:
            resp = self._post(2**32)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["code"], "invalid_friend_id")
        ensure.assert_not_called()
        self.assertIsNone(self._reload().steam_account_id)

    def test_duplicate_409(self) -> None:
        _make_profile_user("pu-other", steam_account_id=515151)
        with patch(ENSURE) as ensure:
            resp = self._post(515151)
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(
            resp.data, {"error": "This Friend ID is already linked to another account"}
        )
        ensure.assert_not_called()

    def test_integrity_error_409(self) -> None:
        other = _make_profile_user("pu-racer")

        def claim_first(*_args: object, **_kwargs: object) -> bool:
            CustomUser.objects.filter(pk=other.pk).update(steam_account_id=525252)
            return True

        with (
            patch(ENSURE, side_effect=claim_first),
            patch("app.functions.user.validate_friend_id", return_value=525252),
        ):
            resp = self._post(525252)
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(
            resp.data, {"error": "This Friend ID is already linked to another account"}
        )
        self.assertIsNone(self._reload().steam_account_id)

    def test_rate_limited_429(self) -> None:
        with patch(ENSURE, side_effect=SteamLookupRateLimited()):
            resp = self._post(424242)
        self.assertEqual(resp.status_code, 429)
        self.assertEqual(resp.data["code"], "steam_lookup_rate_limited")
        self.assertIsNone(self._reload().steam_account_id)

    def test_lookup_unavailable_saves_unverified(self) -> None:
        with patch(ENSURE, return_value=None):
            resp = self._post(434343)
        self.assertEqual(resp.status_code, 201)
        user = self._reload()
        self.assertEqual(user.steam_account_id, 434343)
        self.assertFalse(user.steam_account_verified)
        self.assertIsNone(user.steam_account_exists_checked_at)

    def test_confirmed_sets_exists_checked(self) -> None:
        cache.set(cached_exists_key(444444), True)
        with patch(ENSURE, return_value=True):
            resp = self._post(444444)
        self.assertEqual(resp.status_code, 201)
        user = self._reload()
        self.assertEqual(user.steam_account_id, 444444)
        self.assertIsNotNone(user.steam_account_exists_checked_at)
        self.assertFalse(user.steam_account_verified)

    def test_change_resets_verification(self) -> None:
        self.user.steam_account_id = 454545
        self.user.save()
        self.assertTrue(mark_steam_account_verified(self.user, self.staff, org_id=None))
        self.client.force_authenticate(self._reload())
        with patch(ENSURE, return_value=True):
            resp = self._post(464646)
        self.assertEqual(resp.status_code, 201)
        user = self._reload()
        self.assertEqual(user.steam_account_id, 464646)
        self.assertFalse(user.steam_account_verified)
        self.assertIsNone(user.steam_account_verified_by_id)

    def test_profile_update_same_id_keeps_verification(self) -> None:
        self.user.steam_account_id = 474747
        self.user.save()
        stale = self._reload()
        self.assertTrue(mark_steam_account_verified(self.user, self.staff, org_id=None))
        self.client.force_authenticate(stale)
        with patch(ENSURE) as ensure:
            resp = self.client.post(
                URL, {"steam_account_id": 474747, "nickname": "same"}, format="json"
            )
        self.assertEqual(resp.status_code, 201)
        ensure.assert_not_called()
        user = self._reload()
        self.assertEqual(user.nickname, "same")
        self.assertTrue(user.steam_account_verified)
        self.assertEqual(user.steam_account_verified_by_id, self.staff.pk)

    def test_null_does_not_clear(self) -> None:
        self.user.steam_account_id = 484848
        self.user.save()
        self.client.force_authenticate(self._reload())
        with patch(ENSURE) as ensure:
            resp = self._post(None)
        self.assertEqual(resp.status_code, 201)
        ensure.assert_not_called()
        self.assertEqual(self._reload().steam_account_id, 484848)


@LOOKUP_ON
class ProfileUpdateLookupOutsideAtomicTest(TransactionTestCase):
    def setUp(self) -> None:
        cache.clear()

    def test_lookup_runs_outside_atomic(self) -> None:
        user = _make_profile_user("pu-atomic")
        client = APIClient()
        client.force_authenticate(user)
        seen: list[bool] = []

        def ensure(*_args: object, **_kwargs: object) -> bool:
            seen.append(connection.in_atomic_block)
            return True

        with patch(ENSURE, side_effect=ensure):
            resp = client.post(URL, {"steam_account_id": 494949}, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(seen, [False])
        self.assertEqual(CustomUser.objects.get(pk=user.pk).steam_account_id, 494949)
