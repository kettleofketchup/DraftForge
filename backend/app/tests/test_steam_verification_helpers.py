from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from app.models import CustomUser
from app.steam_accounts import (
    clear_steam_account_verification,
    mark_steam_account_verified,
    steam_verification_payload,
)
from org.models import Organization

BASE = CustomUser.STEAM_ID_64_BASE


class SteamVerificationHelperTests(TestCase):
    def setUp(self) -> None:
        self.actor = CustomUser.objects.create(username="svh-actor")
        self.other_actor = CustomUser.objects.create(username="svh-actor-2")
        self.org = Organization.objects.create(name="SVH Org")
        self.user = CustomUser.objects.create(username="svh-user", steam_account_id=111)

    def _reload(self) -> CustomUser:
        return CustomUser.objects.get(pk=self.user.pk)

    def test_mark_verified_compare_and_set(self) -> None:
        before = timezone.now()
        self.assertTrue(
            mark_steam_account_verified(
                self.user, self.actor, org_id=self.org.pk, expected_id=111
            )
        )
        u = self._reload()
        self.assertEqual(u.steam_account_verified_by_id, self.actor.pk)
        self.assertEqual(u.steam_account_verified_org_id, self.org.pk)
        self.assertIsNotNone(u.steam_account_verified_at)
        self.assertGreaterEqual(u.steam_account_verified_at, before)
        self.assertTrue(self.user.steam_account_verified)
        self.assertEqual(self.user.steam_account_verified_org_id, self.org.pk)

    def test_mark_verified_id_changed_returns_false(self) -> None:
        self.assertFalse(
            mark_steam_account_verified(
                self.user, self.actor, org_id=self.org.pk, expected_id=222
            )
        )
        u = self._reload()
        self.assertIsNone(u.steam_account_verified_at)
        self.assertIsNone(u.steam_account_verified_by_id)
        self.assertFalse(self.user.steam_account_verified)

    def test_mark_verified_idempotent_keeps_original(self) -> None:
        mark_steam_account_verified(self.user, self.actor, org_id=self.org.pk)
        first = self._reload()
        fresh = self._reload()
        self.assertTrue(
            mark_steam_account_verified(
                fresh, self.other_actor, org_id=None, expected_id=111
            )
        )
        u = self._reload()
        self.assertEqual(u.steam_account_verified_at, first.steam_account_verified_at)
        self.assertEqual(u.steam_account_verified_by_id, self.actor.pk)
        self.assertEqual(u.steam_account_verified_org_id, self.org.pk)
        self.assertEqual(fresh.steam_account_verified_by_id, self.actor.pk)

    def test_mark_verified_no_id_raises(self) -> None:
        bare = CustomUser.objects.create(username="svh-bare")
        with self.assertRaises(ValueError):
            mark_steam_account_verified(bare, self.actor, org_id=None)
        with self.assertRaises(ValueError):
            mark_steam_account_verified(bare, self.actor, org_id=None, save=False)
        with self.assertRaises(ValueError):
            clear_steam_account_verification(bare)

    def test_clear_verification(self) -> None:
        mark_steam_account_verified(self.user, self.actor, org_id=self.org.pk)
        self.assertFalse(clear_steam_account_verification(self.user, expected_id=222))
        self.assertTrue(self._reload().steam_account_verified)
        self.assertTrue(clear_steam_account_verification(self.user, expected_id=111))
        u = self._reload()
        self.assertIsNone(u.steam_account_verified_at)
        self.assertIsNone(u.steam_account_verified_by_id)
        self.assertIsNone(u.steam_account_verified_org_id)
        self.assertFalse(self.user.steam_account_verified)
        self.assertTrue(clear_steam_account_verification(self.user))

    def test_mark_verified_save_false_assigns_only(self) -> None:
        self.assertTrue(
            mark_steam_account_verified(
                self.user, self.actor, org_id=self.org.pk, save=False
            )
        )
        self.assertIsNone(self._reload().steam_account_verified_at)
        self.user.save()
        u = self._reload()
        self.assertIsNotNone(u.steam_account_verified_at)
        self.assertEqual(u.steam_account_verified_by_id, self.actor.pk)
        self.assertEqual(u.steam_account_verified_org_id, self.org.pk)

    def test_save_false_with_new_id_verifies_new_id(self) -> None:
        mark_steam_account_verified(self.user, self.actor, org_id=self.org.pk)
        u = self._reload()
        old_at = u.steam_account_verified_at
        u.steam_account_id = 333
        self.assertTrue(
            mark_steam_account_verified(u, self.other_actor, org_id=None, save=False)
        )
        u.save()
        u = self._reload()
        self.assertEqual(u.steam_account_id, 333)
        self.assertEqual(u.steam_account_verified_by_id, self.other_actor.pk)
        self.assertIsNone(u.steam_account_verified_org_id)
        self.assertNotEqual(u.steam_account_verified_at, old_at)

    def test_save_false_expected_id_mismatch(self) -> None:
        self.assertFalse(
            mark_steam_account_verified(
                self.user, self.actor, org_id=None, expected_id=999, save=False
            )
        )
        self.assertIsNone(self.user.steam_account_verified_at)

    def test_instance_save_after_mark_keeps_verification(self) -> None:
        stale = self._reload()
        mark_steam_account_verified(self.user, self.actor, org_id=self.org.pk)
        self.user.save()
        stale.save()
        self.assertTrue(self._reload().steam_account_verified)

    def test_mutators_invalidate_and_log(self) -> None:
        with (
            patch("app.steam_accounts.invalidate_after_commit") as inv,
            patch("app.steam_accounts.log") as log,
        ):
            mark_steam_account_verified(self.user, self.actor, org_id=self.org.pk)
            inv.assert_called_once_with(self.user)
            log.info.assert_called_once()
            args, kwargs = log.info.call_args
            self.assertEqual(args[0], "steam_account_verification_changed")
            self.assertEqual(kwargs["system"], "user")
            self.assertEqual(kwargs["subsystem"], "steam")
            self.assertEqual(kwargs["user_id"], self.user.pk)
            self.assertEqual(kwargs["actor_id"], self.actor.pk)
            self.assertEqual(kwargs["org_id"], self.org.pk)
            self.assertTrue(kwargs["verified"])
            inv.reset_mock()
            log.reset_mock()
            clear_steam_account_verification(self.user)
            inv.assert_called_once_with(self.user)
            self.assertFalse(log.info.call_args.kwargs["verified"])

    def test_failed_compare_and_set_does_not_invalidate(self) -> None:
        with patch("app.steam_accounts.invalidate_after_commit") as inv:
            mark_steam_account_verified(
                self.user, self.actor, org_id=None, expected_id=999
            )
            inv.assert_not_called()

    def test_payload_urls_and_can_verify(self) -> None:
        superuser = CustomUser.objects.create_superuser(
            username="svh-super", password="x", email="svh@example.com"
        )
        mark_steam_account_verified(self.user, superuser, org_id=self.org.pk)
        own = steam_verification_payload(self.user, viewer=self.user)
        self.assertEqual(own["steam_account_id"], 111)
        self.assertTrue(own["steam_account_verified"])
        self.assertIsNotNone(own["steam_account_verified_at"])
        self.assertEqual(own["steam_account_verified_org_name"], "SVH Org")
        self.assertFalse(own["steam_account_exists_checked"])
        self.assertEqual(
            own["steam_profile_url"],
            f"https://steamcommunity.com/profiles/{111 + BASE}",
        )
        self.assertEqual(own["dotabuff_url"], "https://www.dotabuff.com/players/111")
        self.assertFalse(own["can_verify"])
        self.assertTrue(
            steam_verification_payload(self.user, viewer=superuser)["can_verify"]
        )
        self.assertEqual(
            set(own),
            {
                "steam_account_id",
                "steam_account_verified",
                "steam_account_verified_at",
                "steam_account_verified_org_name",
                "steam_account_exists_checked",
                "steam_profile_url",
                "dotabuff_url",
                "can_verify",
            },
        )

    def test_payload_without_id(self) -> None:
        bare = CustomUser.objects.create(username="svh-bare-2")
        payload = steam_verification_payload(bare, viewer=self.actor)
        self.assertIsNone(payload["steam_account_id"])
        self.assertIsNone(payload["steam_profile_url"])
        self.assertIsNone(payload["dotabuff_url"])
        self.assertFalse(payload["steam_account_verified"])
        self.assertIsNone(payload["steam_account_verified_org_name"])
        self.assertFalse(payload["can_verify"])
