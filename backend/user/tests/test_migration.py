import importlib
import unittest

# django-test-migrations is a dev dep added by T1.4. The CI backend-dev image
# is pulled from GHCR and may pre-date this dep until the image-build workflow
# republishes. Skip the whole module cleanly rather than failing with
# ModuleNotFoundError when the image is stale.
try:
    from django_test_migrations.contrib.unittest_case import MigratorTestCase
except ImportError as _import_error:  # pragma: no cover
    raise unittest.SkipTest(
        "django-test-migrations not installed — rebuild backend-dev image "
        "to pick up the new dev dep from pyproject.toml."
    ) from _import_error


class BackfillBaseProfilesMigrationTest(MigratorTestCase):
    migrate_from = ("user", "0001_initial")
    migrate_to = ("user", "0002_backfill_base_profiles")

    def prepare(self):
        # Bypass auto-create signal by using the historical model from old_state.
        # Historical models do not run CustomUser.save() overrides, so we must
        # supply the NOT NULL `positions` FK ourselves.
        CustomUser = self.old_state.apps.get_model("app", "CustomUser")
        PositionsModel = self.old_state.apps.get_model("app", "PositionsModel")
        positions = PositionsModel.objects.create()
        CustomUser.objects.create(
            username="alice",
            nickname="Alice Old",
            avatar="https://example.com/alice.png",
            positions=positions,
        )
        CustomUser.objects.create(
            username="bob",
            nickname=None,
            avatar=None,
            positions=PositionsModel.objects.create(),
        )

    def test_each_user_gets_base_profile_with_copied_values(self):
        BaseUserProfile = self.new_state.apps.get_model("user", "BaseUserProfile")
        alice = BaseUserProfile.objects.get(user__username="alice")
        bob = BaseUserProfile.objects.get(user__username="bob")
        assert alice.nickname == "Alice Old"
        assert alice.avatar == "https://example.com/alice.png"
        assert bob.nickname is None
        assert bob.avatar is None


class BackfillIdempotencyTest(MigratorTestCase):
    """Re-running the forward backfill on existing rows must be a no-op.

    Real-world scenarios this defends:
      - Deploy retry after a partial migration (a few rows succeeded, the
        transaction rolled back, then it's re-applied).
      - A future re-baseline that runs the forward function out-of-band.

    The implementation relies on bulk_create(ignore_conflicts=True) +
    BaseUserProfile.user being unique (OneToOne). If either guarantee is
    weakened in T2/T3, this test catches it.
    """

    migrate_from = ("user", "0001_initial")
    migrate_to = ("user", "0002_backfill_base_profiles")

    def prepare(self):
        CustomUser = self.old_state.apps.get_model("app", "CustomUser")
        PositionsModel = self.old_state.apps.get_model("app", "PositionsModel")
        CustomUser.objects.create(
            username="carol",
            nickname="Carol Initial",
            avatar=None,
            positions=PositionsModel.objects.create(),
        )

    def test_running_forward_again_does_not_duplicate_or_overwrite(self):
        BaseUserProfile = self.new_state.apps.get_model("user", "BaseUserProfile")
        CustomUser = self.new_state.apps.get_model("app", "CustomUser")

        # State after first run
        before = BaseUserProfile.objects.count()
        carol = BaseUserProfile.objects.get(user__username="carol")
        # Sanity: backfill copied the original nickname through.
        assert carol.nickname == "Carol Initial"

        # Simulate a follow-on change that happened AFTER the backfill — the
        # nickname was updated via the new PATCH endpoint. A second
        # accidental run of the forward function must NOT clobber this back
        # to "Carol Initial".
        carol.nickname = "Carol Renamed"
        carol.save()

        # Re-import the migration module and re-execute the forward function
        # using the new_state apps registry (where BaseUserProfile lives).
        module = importlib.import_module(
            "user.migrations.0002_backfill_base_profiles"
        )
        module.copy_nickname_avatar_to_base_profile(self.new_state.apps, None)

        after = BaseUserProfile.objects.count()
        assert after == before, (
            f"Backfill rerun changed row count: before={before}, after={after} — "
            "ignore_conflicts=True guarantee broken"
        )
        carol_after = BaseUserProfile.objects.get(user__username="carol")
        assert carol_after.nickname == "Carol Renamed", (
            "Backfill rerun overwrote a row that had been edited post-backfill — "
            "the data migration is destructive and must be made INSERT-only"
        )

        # Sanity: CustomUser row count unchanged too.
        assert CustomUser.objects.count() == 1


class BackfillReverseTest(MigratorTestCase):
    """The reverse path copies BaseUserProfile nickname/avatar back onto
    CustomUser. Exercised by `migrate user 0001` after `0002` has run."""

    migrate_from = ("user", "0001_initial")
    migrate_to = ("user", "0002_backfill_base_profiles")

    def prepare(self):
        CustomUser = self.old_state.apps.get_model("app", "CustomUser")
        PositionsModel = self.old_state.apps.get_model("app", "PositionsModel")
        CustomUser.objects.create(
            username="dora",
            nickname="Dora Initial",
            avatar="dora_avatar_hash",
            positions=PositionsModel.objects.create(),
        )

    def test_reverse_copies_base_profile_values_back_to_customuser(self):
        BaseUserProfile = self.new_state.apps.get_model("user", "BaseUserProfile")
        CustomUser = self.new_state.apps.get_model("app", "CustomUser")

        # Mutate the base profile post-backfill — reverse should copy this
        # NEW value back to CustomUser (not the original from prepare).
        dora_bp = BaseUserProfile.objects.get(user__username="dora")
        dora_bp.nickname = "Dora Edited Post-Migrate"
        dora_bp.avatar = "new_avatar_hash"
        dora_bp.save()

        module = importlib.import_module(
            "user.migrations.0002_backfill_base_profiles"
        )
        module.reverse_copy(self.new_state.apps, None)

        dora_user = CustomUser.objects.get(username="dora")
        assert dora_user.nickname == "Dora Edited Post-Migrate"
        assert dora_user.avatar == "new_avatar_hash"
