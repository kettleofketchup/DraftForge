import importlib
import unittest

from structlog.testing import capture_logs

# django-test-migrations is a dev dep; a stale CI image may lack it.
try:
    from django_test_migrations.contrib.unittest_case import MigratorTestCase
except ImportError as _import_error:  # pragma: no cover
    raise unittest.SkipTest(
        "django-test-migrations not installed — rebuild backend-dev image "
        "to pick up the new dev dep from pyproject.toml."
    ) from _import_error

STEAM_ID_64_BASE = 76561197960265728


class SteamAccountIdBackfillMigrationTest(MigratorTestCase):
    """app 0114: profile Friend IDs move onto empty CustomUser.steam_account_id."""

    migrate_from = [
        ("app", "0113_widen_steam_account_id"),
        ("org", "0014_move_organization_models_from_app"),
    ]
    migrate_to = ("app", "0114_copy_profile_friend_ids")

    def prepare(self) -> None:
        apps = self.old_state.apps
        CustomUser = apps.get_model("app", "CustomUser")
        Organization = apps.get_model("org", "Organization")
        OrgUser = apps.get_model("org", "OrgUser")
        Dota = apps.get_model("org", "PlayerDotaProfile")
        Deadlock = apps.get_model("org", "PlayerDeadlockProfile")
        org_a = Organization.objects.create(name="Backfill A")
        org_b = Organization.objects.create(name="Backfill B")

        def member(name: str, org: object, **user_fields: object) -> object:
            user, _ = CustomUser.objects.get_or_create(
                username=name, defaults=user_fields
            )
            return OrgUser.objects.create(user=user, organization=org)

        self.ids: dict[str, int] = {}

        single = member("single", org_a)
        Dota.objects.create(org_user=single, unverified_friend_id=" 04242 ")
        Deadlock.objects.create(org_user=single, unverified_friend_id="4242")
        Dota.objects.create(
            org_user=member("single", org_b), unverified_friend_id="abc"
        )
        self.ids["single"] = single.user_id

        wide = member("wide", org_a)
        Deadlock.objects.create(org_user=wide, unverified_friend_id=str(2**32 - 1))
        self.ids["wide"] = wide.user_id

        ambiguous = member("ambiguous", org_a)
        Dota.objects.create(org_user=ambiguous, unverified_friend_id="111")
        Dota.objects.create(
            org_user=member("ambiguous", org_b), unverified_friend_id="222"
        )
        self.ids["ambiguous"] = ambiguous.user_id

        member("holder", org_a, steam_account_id=5150)
        taken = member("taken", org_a)
        Dota.objects.create(org_user=taken, unverified_friend_id="5150")
        self.ids["taken"] = taken.user_id

        for name in ("contested_1", "contested_2"):
            ou = member(name, org_a)
            Deadlock.objects.create(org_user=ou, unverified_friend_id="6060")
            self.ids[name] = ou.user_id

        already = member("already", org_a, steam_account_id=7070)
        Dota.objects.create(org_user=already, unverified_friend_id="8080")
        self.ids["already"] = already.user_id

        invalid = member("invalid", org_a)
        Dota.objects.create(org_user=invalid, unverified_friend_id="0")
        Deadlock.objects.create(org_user=invalid, unverified_friend_id=str(2**32))
        self.ids["invalid"] = invalid.user_id

    def _account_ids(self) -> dict[str, int | None]:
        CustomUser = self.new_state.apps.get_model("app", "CustomUser")
        stored = dict(
            CustomUser.objects.filter(pk__in=self.ids.values()).values_list(
                "pk", "steam_account_id"
            )
        )
        return {name: stored[pk] for name, pk in self.ids.items()}

    def test_backfill(self) -> None:
        self.assertEqual(
            self._account_ids(),
            {
                "single": 4242,
                "wide": 2**32 - 1,
                "ambiguous": None,
                "taken": None,
                "contested_1": None,
                "contested_2": None,
                "already": 7070,
                "invalid": None,
            },
        )
        CustomUser = self.new_state.apps.get_model("app", "CustomUser")
        self.assertEqual(
            CustomUser.objects.get(pk=self.ids["single"]).steamid,
            4242 + STEAM_ID_64_BASE,
        )

    def test_rerun_is_idempotent_and_logs_skips(self) -> None:
        before = self._account_ids()
        migration = importlib.import_module(
            "app.migrations.0114_copy_profile_friend_ids"
        )
        with capture_logs() as logs:
            migration.copy_profile_friend_ids(self.new_state.apps, None)
        self.assertEqual(self._account_ids(), before)
        skips = {
            entry["user_id"]: entry["reason"]
            for entry in logs
            if entry["event"] == "steam_friend_id_backfill_skipped"
        }
        self.assertEqual(
            skips,
            {
                self.ids["ambiguous"]: "ambiguous",
                self.ids["taken"]: "taken",
                self.ids["contested_1"]: "taken",
                self.ids["contested_2"]: "taken",
            },
        )
