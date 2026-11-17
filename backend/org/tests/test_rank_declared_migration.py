import unittest

# django-test-migrations is a dev dep; a stale CI image may lack it.
try:
    from django_test_migrations.contrib.unittest_case import MigratorTestCase
except ImportError as _import_error:  # pragma: no cover
    raise unittest.SkipTest(
        "django-test-migrations not installed — rebuild backend-dev image "
        "to pick up the new dev dep from pyproject.toml."
    ) from _import_error


class RankDeclaredMigrationTest(MigratorTestCase):
    migrate_from = ("org", "0010_orguser_guild_nickname")
    migrate_to = ("org", "0011_playerdotaprofile_rank_declared_at")

    def prepare(self) -> None:
        apps = self.old_state.apps
        CustomUser = apps.get_model("app", "CustomUser")
        Organization = apps.get_model("app", "Organization")
        OrgUser = apps.get_model("org", "OrgUser")
        Profile = apps.get_model("org", "PlayerDotaProfile")
        org = Organization.objects.create(name="Org")

        def profile(key: str, **fields: object) -> int:
            user = CustomUser.objects.create(username=key)
            ou = OrgUser.objects.create(user=user, organization=org)
            return Profile.objects.create(org_user=ou, **fields).pk

        self.pks = {
            "active": profile("active", rank_status="active"),
            "screenshot": profile(
                "screenshot", rank_status="never", rank_screenshot="x"
            ),
            "battlecup_shot": profile(
                "battlecup_shot", rank_status="never", battlecup_screenshot="x"
            ),
            "medal": profile("medal", rank_status="never", rank_medal="Herald"),
            "tier": profile("tier", rank_status="never", battle_cup_tier=3),
            "default": profile("default", rank_status="never"),
        }

    def test_declared(self) -> None:
        Profile = self.new_state.apps.get_model("org", "PlayerDotaProfile")
        declared = {
            key: Profile.objects.get(pk=pk).rank_declared_at is not None
            for key, pk in self.pks.items()
        }
        self.assertEqual(
            declared,
            {
                "active": True,
                "screenshot": True,
                "battlecup_shot": True,
                "medal": True,
                "tier": True,
                "default": False,
            },
        )
