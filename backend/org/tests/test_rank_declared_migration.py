import unittest

from org.tests.rank_evidence_cases import RANK_EVIDENCE_CASES

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
            key: profile(key, **fields)
            for key, (fields, _) in RANK_EVIDENCE_CASES.items()
        }

    def test_declared(self) -> None:
        Profile = self.new_state.apps.get_model("org", "PlayerDotaProfile")
        declared = {
            key: Profile.objects.get(pk=pk).rank_declared_at is not None
            for key, pk in self.pks.items()
        }
        self.assertEqual(
            declared,
            {key: expected for key, (_, expected) in RANK_EVIDENCE_CASES.items()},
        )
