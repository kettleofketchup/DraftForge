from django.test import TestCase
from django.utils import timezone

from app.models import CustomUser
from org.models import Organization

BASE = CustomUser.STEAM_ID_64_BASE


class SteamVerificationModelTests(TestCase):
    def setUp(self) -> None:
        self.staff = CustomUser.objects.create(username="sv-staff")
        self.org = Organization.objects.create(name="SV Org")
        self.user = CustomUser.objects.create(username="sv-user", steam_account_id=111)

    def _reload(self) -> CustomUser:
        return CustomUser.objects.get(pk=self.user.pk)

    def _verify_in_db(self) -> None:
        CustomUser.objects.filter(pk=self.user.pk).update(
            steam_account_verified_at=timezone.now(),
            steam_account_verified_by=self.staff,
            steam_account_verified_org=self.org,
            steam_account_exists_checked_at=timezone.now(),
        )

    def _assert_unverified(self, u: CustomUser) -> None:
        self.assertIsNone(u.steam_account_verified_at)
        self.assertIsNone(u.steam_account_verified_by_id)
        self.assertIsNone(u.steam_account_verified_org_id)

    def test_new_user_with_id_is_unverified(self) -> None:
        u = self._reload()
        self.assertEqual(u.steam_account_id, 111)
        self._assert_unverified(u)
        self.assertIsNone(u.steam_account_exists_checked_at)
        self.assertFalse(u.steam_account_verified)

    def test_id_change_clears_verification_and_exists(self) -> None:
        self._verify_in_db()
        u = self._reload()
        u.steam_account_id = 222
        u.save()
        u = self._reload()
        self._assert_unverified(u)
        self.assertIsNone(u.steam_account_exists_checked_at)
        self.assertEqual(u.steamid, 222 + BASE)

    def test_explicit_clear_clears_both_ids(self) -> None:
        self._verify_in_db()
        u = self._reload()
        u.steam_account_id = None
        u.save()
        u = self._reload()
        self.assertIsNone(u.steam_account_id)
        self.assertIsNone(u.steamid)
        self._assert_unverified(u)
        self.assertIsNone(u.steam_account_exists_checked_at)

    def test_update_fields_save_persists_reset(self) -> None:
        self._verify_in_db()
        u = self._reload()
        u.steam_account_id = 222
        u.save(update_fields=["steam_account_id", "steamid"])
        u = self._reload()
        self.assertEqual(u.steam_account_id, 222)
        self._assert_unverified(u)
        self.assertIsNone(u.steam_account_exists_checked_at)

    def test_steamid_only_write_sets_id_unverified(self) -> None:
        u = CustomUser.objects.create(username="sv-noid")
        u = CustomUser.objects.get(pk=u.pk)
        u.steamid = 333 + BASE
        u.save()
        u = CustomUser.objects.get(pk=u.pk)
        self.assertEqual(u.steam_account_id, 333)
        self._assert_unverified(u)

    def test_steamid_only_change_wins_when_id_unchanged(self) -> None:
        self._verify_in_db()
        u = self._reload()
        u.steamid = 444 + BASE
        u.save()
        u = self._reload()
        self.assertEqual(u.steam_account_id, 444)
        self.assertEqual(u.steamid, 444 + BASE)
        self._assert_unverified(u)

    def test_new_id_with_verification_in_same_save_is_kept(self) -> None:
        self._verify_in_db()
        u = self._reload()
        u.steam_account_id = 555
        u.steam_account_verified_at = timezone.now()
        u.steam_account_verified_by = self.staff
        u.save()
        u = self._reload()
        self.assertEqual(u.steam_account_id, 555)
        self.assertIsNotNone(u.steam_account_verified_at)
        self.assertEqual(u.steam_account_verified_by_id, self.staff.pk)
        self.assertIsNone(u.steam_account_exists_checked_at)

    def test_noop_save_keeps_verification(self) -> None:
        self._verify_in_db()
        u = self._reload()
        u.save()
        u = self._reload()
        self.assertIsNotNone(u.steam_account_verified_at)
        self.assertEqual(u.steam_account_verified_by_id, self.staff.pk)
        self.assertEqual(u.steam_account_verified_org_id, self.org.pk)
        self.assertIsNotNone(u.steam_account_exists_checked_at)

    def test_stale_full_save_keeps_verification(self) -> None:
        stale = self._reload()
        CustomUser.objects.filter(pk=self.user.pk).update(
            steam_account_verified_at=timezone.now()
        )
        stale.discordNickname = "x"
        stale.save()
        u = self._reload()
        self.assertIsNotNone(u.steam_account_verified_at)
        self.assertEqual(u.discordNickname, "x")

    def test_stale_full_save_keeps_newer_id_and_verification(self) -> None:
        stale = self._reload()
        CustomUser.objects.filter(pk=self.user.pk).update(
            steam_account_id=222,
            steamid=222 + BASE,
            steam_account_verified_at=timezone.now(),
        )
        stale.discordNickname = "x"
        stale.save()
        u = self._reload()
        self.assertEqual(u.steam_account_id, 222)
        self.assertEqual(u.steamid, 222 + BASE)
        self.assertIsNotNone(u.steam_account_verified_at)
        self.assertEqual(u.discordNickname, "x")

    def test_refresh_from_db_updates_snapshot(self) -> None:
        u = self._reload()
        CustomUser.objects.filter(pk=self.user.pk).update(
            steam_account_id=222,
            steamid=222 + BASE,
            steam_account_verified_at=timezone.now(),
        )
        u.refresh_from_db(fields=["steam_account_id", "steamid"])
        u.save(update_fields=["steam_account_id", "steamid"])
        u = self._reload()
        self.assertEqual(u.steam_account_id, 222)
        self.assertIsNotNone(u.steam_account_verified_at)

    def test_deferred_load_save_keeps_verification(self) -> None:
        self._verify_in_db()
        u = CustomUser.objects.only("pk", "discordNickname").get(pk=self.user.pk)
        u.discordNickname = "y"
        u.save()
        u = self._reload()
        self.assertEqual(u.discordNickname, "y")
        self.assertEqual(u.steam_account_id, 111)
        self.assertIsNotNone(u.steam_account_verified_at)

    def test_property_steam_account_verified(self) -> None:
        self.assertFalse(self._reload().steam_account_verified)
        self._verify_in_db()
        self.assertTrue(self._reload().steam_account_verified)
