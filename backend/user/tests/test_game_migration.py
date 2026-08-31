import importlib
import unittest

# django-test-migrations is a dev dep (lesson #22). The CI backend-dev image is
# pulled from GHCR and may pre-date this dep until the image-build workflow
# republishes. Skip the whole module cleanly rather than failing with
# ModuleNotFoundError when the image is stale.
try:
    from django_test_migrations.contrib.unittest_case import MigratorTestCase
except ImportError as _import_error:  # pragma: no cover
    raise unittest.SkipTest(
        "django-test-migrations not installed — rebuild backend-dev image "
        "to pick up the new dev dep from pyproject.toml."
    ) from _import_error


class BackfillGameProfilesTest(MigratorTestCase):
    migrate_from = ("user", "0003_dota_deadlock_user_profiles")
    migrate_to = ("user", "0004_backfill_game_profiles")

    def prepare(self):
        CustomUser = self.old_state.apps.get_model("app", "CustomUser")
        PositionsModel = self.old_state.apps.get_model("app", "PositionsModel")
        BaseUserProfile = self.old_state.apps.get_model("user", "BaseUserProfile")
        pos = PositionsModel.objects.create(carry=4, mid=2)
        u = CustomUser.objects.create(
            username="mig",
            positions=pos,
            has_active_dota_mmr=True,
        )
        # T1 historical save does NOT auto-create base_profile (historical model);
        # create it explicitly so 0004 has a parent to attach to.
        BaseUserProfile.objects.get_or_create(user_id=u.pk)

    def test_dota_profile_backfilled_with_positions_and_mmr(self):
        DotaUserProfile = self.new_state.apps.get_model("user", "DotaUserProfile")
        DeadlockUserProfile = self.new_state.apps.get_model(
            "user", "DeadlockUserProfile"
        )
        dota = DotaUserProfile.objects.get(base_profile__user__username="mig")
        assert dota.positions.carry == 4
        assert dota.has_active_dota_mmr is True
        # every base profile also got a (empty) deadlock profile
        assert DeadlockUserProfile.objects.filter(
            base_profile__user__username="mig"
        ).exists()


class BackfillIdempotencyTest(MigratorTestCase):
    """Re-running the forward backfill on existing rows must be a no-op.

    Real-world scenarios this defends:
      - Deploy retry after a partial migration (a few rows succeeded, the
        transaction rolled back, then it's re-applied).
      - A future re-baseline that runs the forward function out-of-band.

    The implementation relies on bulk_create(ignore_conflicts=True) +
    existence checks per base_profile. If either guarantee is weakened, this
    test catches it.
    """

    migrate_from = ("user", "0003_dota_deadlock_user_profiles")
    migrate_to = ("user", "0004_backfill_game_profiles")

    def prepare(self):
        CustomUser = self.old_state.apps.get_model("app", "CustomUser")
        PositionsModel = self.old_state.apps.get_model("app", "PositionsModel")
        BaseUserProfile = self.old_state.apps.get_model("user", "BaseUserProfile")
        pos = PositionsModel.objects.create(carry=3)
        u = CustomUser.objects.create(
            username="idem",
            positions=pos,
            has_active_dota_mmr=False,
        )
        BaseUserProfile.objects.get_or_create(user_id=u.pk)

    def test_running_forward_again_does_not_duplicate_or_overwrite(self):
        DotaUserProfile = self.new_state.apps.get_model("user", "DotaUserProfile")
        DeadlockUserProfile = self.new_state.apps.get_model(
            "user", "DeadlockUserProfile"
        )

        # State after first run
        dota_before = DotaUserProfile.objects.count()
        deadlock_before = DeadlockUserProfile.objects.count()

        # Simulate a follow-on change that happened AFTER the backfill — the
        # MMR flag was flipped via the new endpoint. A second accidental run of
        # the forward function must NOT clobber this back to False.
        dota = DotaUserProfile.objects.get(base_profile__user__username="idem")
        dota.has_active_dota_mmr = True
        dota.save()

        # Re-import the migration module and re-execute the forward function
        # using the new_state apps registry (where the game profiles live).
        module = importlib.import_module(
            "user.migrations.0004_backfill_game_profiles"
        )
        module.backfill_game_profiles(self.new_state.apps, None)

        dota_after = DotaUserProfile.objects.count()
        deadlock_after = DeadlockUserProfile.objects.count()
        assert dota_after == dota_before, (
            f"Backfill rerun changed Dota row count: before={dota_before}, "
            f"after={dota_after} — INSERT-only guarantee broken"
        )
        assert deadlock_after == deadlock_before, (
            f"Backfill rerun changed Deadlock row count: "
            f"before={deadlock_before}, after={deadlock_after}"
        )
        dota_reloaded = DotaUserProfile.objects.get(
            base_profile__user__username="idem"
        )
        assert dota_reloaded.has_active_dota_mmr is True, (
            "Backfill rerun overwrote a row that had been edited post-backfill — "
            "the data migration is destructive and must be made INSERT-only"
        )


class BackfillReverseTest(MigratorTestCase):
    """The reverse path copies DotaUserProfile positions/mmr back onto
    CustomUser. Exercised by `migrate user 0003` after `0004` has run."""

    migrate_from = ("user", "0003_dota_deadlock_user_profiles")
    migrate_to = ("user", "0004_backfill_game_profiles")

    def prepare(self):
        CustomUser = self.old_state.apps.get_model("app", "CustomUser")
        PositionsModel = self.old_state.apps.get_model("app", "PositionsModel")
        BaseUserProfile = self.old_state.apps.get_model("user", "BaseUserProfile")
        pos = PositionsModel.objects.create(carry=1)
        u = CustomUser.objects.create(
            username="rev",
            positions=pos,
            has_active_dota_mmr=False,
        )
        BaseUserProfile.objects.get_or_create(user_id=u.pk)

    def test_reverse_copies_dota_profile_values_back_to_customuser(self):
        DotaUserProfile = self.new_state.apps.get_model("user", "DotaUserProfile")
        PositionsModel = self.new_state.apps.get_model("app", "PositionsModel")
        CustomUser = self.new_state.apps.get_model("app", "CustomUser")

        # Mutate the dota profile post-backfill — reverse should copy these NEW
        # values back to CustomUser (not the originals from prepare).
        new_pos = PositionsModel.objects.create(carry=5, mid=5)
        dota = DotaUserProfile.objects.get(base_profile__user__username="rev")
        dota.positions = new_pos
        dota.has_active_dota_mmr = True
        dota.save()

        module = importlib.import_module(
            "user.migrations.0004_backfill_game_profiles"
        )
        module.reverse_backfill(self.new_state.apps, None)

        rev_user = CustomUser.objects.get(username="rev")
        assert rev_user.positions_id == new_pos.pk
        assert rev_user.has_active_dota_mmr is True
