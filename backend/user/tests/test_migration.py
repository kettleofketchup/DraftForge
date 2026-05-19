from django_test_migrations.contrib.unittest_case import MigratorTestCase


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
