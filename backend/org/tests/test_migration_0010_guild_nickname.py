import unittest

from django.conf import settings
from django.test import override_settings

try:
    from django_test_migrations.contrib.unittest_case import MigratorTestCase
except ImportError as _import_error:  # pragma: no cover
    raise unittest.SkipTest(
        "django-test-migrations not installed — rebuild backend-dev image "
        "to pick up the new dev dep from pyproject.toml."
    ) from _import_error


MIGRATE_FROM = [("org", "0009_promotion"), ("app", "0105_orglog_reopen_event")]
MIGRATE_TO = [("org", "0010_orguser_guild_nickname")]


class CopyDtxGuildNicknamesTest(MigratorTestCase):
    migrate_from = MIGRATE_FROM
    migrate_to = MIGRATE_TO

    def prepare(self) -> None:
        CustomUser = self.old_state.apps.get_model("app", "CustomUser")
        Organization = self.old_state.apps.get_model("app", "Organization")
        OrgUser = self.old_state.apps.get_model("org", "OrgUser")

        dtx = Organization.objects.create(
            name="DTX", discord_server_id=str(settings.DISCORD_GUILD_ID)
        )
        other = Organization.objects.create(name="Other", discord_server_id="999")

        dragon = CustomUser.objects.create(
            username="dragonclaw_m0010", guildNickname="DragonClaw"
        )
        blank = CustomUser.objects.create(username="blank_m0010", guildNickname="")

        self.dragon_dtx_pk = OrgUser.objects.create(user=dragon, organization=dtx).pk
        self.dragon_other_pk = OrgUser.objects.create(
            user=dragon, organization=other
        ).pk
        self.blank_dtx_pk = OrgUser.objects.create(user=blank, organization=dtx).pk

    def test_copies_only_to_dtx_membership(self) -> None:
        OrgUser = self.new_state.apps.get_model("org", "OrgUser")
        self.assertEqual(
            OrgUser.objects.get(pk=self.dragon_dtx_pk).guild_nickname, "DragonClaw"
        )
        self.assertIsNone(OrgUser.objects.get(pk=self.dragon_other_pk).guild_nickname)

    def test_empty_nickname_not_copied(self) -> None:
        OrgUser = self.new_state.apps.get_model("org", "OrgUser")
        self.assertIsNone(OrgUser.objects.get(pk=self.blank_dtx_pk).guild_nickname)


@override_settings(DISCORD_GUILD_ID=None)
class CopyDtxGuildNicknamesNoGuildTest(MigratorTestCase):
    migrate_from = MIGRATE_FROM
    migrate_to = MIGRATE_TO

    def prepare(self) -> None:
        CustomUser = self.old_state.apps.get_model("app", "CustomUser")
        Organization = self.old_state.apps.get_model("app", "Organization")
        OrgUser = self.old_state.apps.get_model("org", "OrgUser")

        dtx = Organization.objects.create(
            name="DTX", discord_server_id="734185035623825559"
        )
        dragon = CustomUser.objects.create(
            username="dragonclaw_m0010_noguild", guildNickname="DragonClaw"
        )
        self.org_user_pk = OrgUser.objects.create(user=dragon, organization=dtx).pk

    def test_noop_without_guild_id(self) -> None:
        OrgUser = self.new_state.apps.get_model("org", "OrgUser")
        self.assertIsNone(OrgUser.objects.get(pk=self.org_user_pk).guild_nickname)
