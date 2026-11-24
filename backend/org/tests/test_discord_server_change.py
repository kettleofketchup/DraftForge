from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings

from app.models import CustomUser
from org.discord_names import reset_org_guild_nicknames
from org.models import Organization, OrgUser

LOCMEM = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "test_discord_server_change",
    }
}
APPLY = "user.tasks.discord_name_sync.sync_org_discord_names.apply_async"


@override_settings(CACHES=LOCMEM)
class DiscordServerChangeTest(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.org = Organization.objects.create(
            name="Switch Org", discord_server_id="111"
        )
        self.other = Organization.objects.create(
            name="Other Org", discord_server_id="111"
        )
        self.user = CustomUser.objects.create_user(username="sw_user", password="x")
        self.org_user = OrgUser.objects.create(
            user=self.user, organization=self.org, guild_nickname="DragonClaw"
        )
        self.other_ou = OrgUser.objects.create(
            user=self.user, organization=self.other, guild_nickname="Other"
        )

    def _nick(self, ou: OrgUser) -> str | None:
        return OrgUser.objects.nocache().get(pk=ou.pk).guild_nickname

    def _save(self, value: str | None) -> mock.MagicMock:
        with mock.patch(APPLY) as apply_async:
            with self.captureOnCommitCallbacks(execute=True):
                org = Organization.objects.nocache().get(pk=self.org.pk)
                org.discord_server_id = value
                org.save()
        return apply_async

    def test_switching_guild_blanks_and_enqueues(self) -> None:
        apply_async = self._save("222")
        self.assertIsNone(self._nick(self.org_user))
        self.assertEqual(self._nick(self.other_ou), "Other")
        apply_async.assert_called_once()
        self.assertEqual(apply_async.call_args.kwargs["args"], [self.org.pk])

    def test_clearing_blanks_without_enqueue(self) -> None:
        apply_async = self._save(None)
        self.assertIsNone(self._nick(self.org_user))
        apply_async.assert_not_called()

    def test_clearing_to_empty_string_blanks_without_enqueue(self) -> None:
        apply_async = self._save("")
        self.assertIsNone(self._nick(self.org_user))
        apply_async.assert_not_called()

    def test_same_value_does_nothing(self) -> None:
        apply_async = self._save("111")
        self.assertEqual(self._nick(self.org_user), "DragonClaw")
        apply_async.assert_not_called()

    def test_other_field_change_does_nothing(self) -> None:
        with mock.patch(APPLY) as apply_async:
            with self.captureOnCommitCallbacks(execute=True):
                org = Organization.objects.nocache().get(pk=self.org.pk)
                org.name = "Renamed"
                org.save()
        self.assertEqual(self._nick(self.org_user), "DragonClaw")
        apply_async.assert_not_called()

    def test_create_does_nothing(self) -> None:
        with mock.patch(APPLY) as apply_async:
            with self.captureOnCommitCallbacks(execute=True):
                Organization.objects.create(name="Fresh", discord_server_id="333")
        apply_async.assert_not_called()

    def test_reset_invalidates_org_users_and_users(self) -> None:
        with mock.patch("org.discord_names.invalidate_after_commit") as spy:
            count = reset_org_guild_nicknames(self.org, enqueue=False)
        self.assertEqual(count, 1)
        args = [a for call in spy.call_args_list for a in call.args]
        self.assertTrue(
            any(isinstance(a, OrgUser) and a.pk == self.org_user.pk for a in args)
        )
        self.assertTrue(
            any(isinstance(a, CustomUser) and a.pk == self.user.pk for a in args)
        )

    def test_reset_evicts_cached_org_user_read(self) -> None:
        OrgUser.objects.get(pk=self.org_user.pk)
        with self.captureOnCommitCallbacks(execute=True):
            reset_org_guild_nicknames(self.org, enqueue=False)
        self.assertIsNone(OrgUser.objects.get(pk=self.org_user.pk).guild_nickname)

    def test_reset_with_no_nicknames_returns_zero(self) -> None:
        empty = Organization.objects.create(name="Empty", discord_server_id="444")
        with mock.patch(APPLY) as apply_async:
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(reset_org_guild_nicknames(empty, enqueue=True), 0)
        apply_async.assert_called_once()
