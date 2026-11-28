from django.contrib import admin
from django.db import transaction
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from social_django.models import UserSocialAuth

from app.admin import CustomUserAdmin
from app.models import CustomUser
from common.game import GameType
from league.mmr import set_league_mmr
from league.models import League, LeagueUser
from org.api_connections.mutations import MmrMutationContext, MmrRevisionConflict
from org.api_tokens.sync import member_rows, sync_mmrs
from org.features import FeatureKey, set_org_feature
from org.mmr import (
    bulk_set_org_mmrs,
    game_mmrs_prefetch,
    get_org_mmr,
    mark_org_mmr_verified,
    merge_org_mmrs,
    set_org_mmr,
)
from org.mmr_official import apply_official_org_mmr
from org.mmr_requests.services import repoint_mmr_requests
from org.models import (
    Organization,
    OrgApiConnection,
    OrgApiMmrDelivery,
    OrgMmrRevisionCounter,
    OrgMmrSyncState,
    OrgUser,
    OrgUserGameMmr,
)
from tournament.management.commands.import_prod_tournament import Command
from tournament.models import Tournament
from user.discord_accounts import merge_discord_accounts
from user.models import ProfileClaimRequest
from user.pipelines import save_discord


class MmrMutationTests(TestCase):
    def setUp(self) -> None:
        self.owner = CustomUser.objects.create_user(username="mutation-admin")
        self.user = CustomUser.objects.create_user(
            username="mutation-player",
            steam_account_id=12345,
            discordId="987654321012345678",
        )
        self.org = Organization.objects.create(name="Mutation Org", owner=self.owner)
        set_org_feature(self.org, FeatureKey.MMR_SYNC, enabled=True, actor=None)
        self.member = OrgUser.objects.create(organization=self.org, user=self.user)
        self.connection = OrgApiConnection.objects.create(
            organization=self.org,
            name="Ratings",
            enabled=True,
            mmr_push_enabled=True,
            outbound_base_url="https://ratings.example",
            outbound_auth="none",
            outbound_authorizer=self.owner,
        )
        self.game = GameType.DOTA2

    def state(self, member: OrgUser | None = None) -> OrgMmrSyncState:
        return OrgMmrSyncState.objects.get(
            org_user=member or self.member, game_type=self.game
        )

    def write(self, value: int) -> None:
        set_org_mmr(self.member, self.game, value, mark_verified=False)

    def test_mutation_path_inventory_set_create_clear(self) -> None:
        self.write(4500)
        first = self.state()
        self.assertGreater(first.revision, 0)
        self.write(0)
        cleared = self.state()
        self.assertEqual(cleared.value, 0)
        self.assertGreater(cleared.revision, first.revision)
        delivery = OrgApiMmrDelivery.objects.latest("pk")
        self.assertEqual(delivery.payload["entries"][0]["mmr"], 0)
        self.assertEqual(delivery.payload["entries"][0]["revision"], cleared.revision)
        self.assertEqual(delivery.destination_origin, "https://ratings.example:443")

    def test_verification_only_advances_without_push(self) -> None:
        self.write(4500)
        before = self.state().revision
        count = OrgApiMmrDelivery.objects.count()
        mark_org_mmr_verified(self.member, self.game, self.owner)
        self.assertGreater(self.state().revision, before)
        self.assertEqual(OrgApiMmrDelivery.objects.count(), count)
        verified = self.state().revision
        bulk_set_org_mmrs(self.org.pk, self.game, {self.user.pk: 4500})
        self.assertGreater(self.state().revision, verified)
        self.assertIsNone(self.state().verified_at)
        self.assertEqual(OrgApiMmrDelivery.objects.count(), count)

    def test_unchanged_numeric_is_noop(self) -> None:
        self.write(4500)
        before = self.state().revision
        self.write(4500)
        self.assertEqual(self.state().revision, before)
        self.assertEqual(OrgApiMmrDelivery.objects.count(), 1)

    def test_official_and_bulk_share_revision_domain(self) -> None:
        apply_official_org_mmr(
            self.member, self.game, 4000, actor=self.owner, source="test"
        )
        before = self.state().revision
        bulk_set_org_mmrs(self.org.pk, self.game, {self.user.pk: 4500})
        self.assertGreater(self.state().revision, before)
        self.assertEqual(self.state().value, 4500)

    def test_rollback_creates_no_state_or_delivery(self) -> None:
        with self.assertRaises(ValueError), transaction.atomic():
            self.write(4000)
            raise ValueError("rollback")
        self.assertFalse(OrgMmrSyncState.objects.filter(org_user=self.member).exists())
        self.assertFalse(OrgApiMmrDelivery.objects.exists())

    def test_same_source_suppression_other_connection_fanout(self) -> None:
        other = OrgApiConnection.objects.create(
            organization=self.org,
            name="Other",
            enabled=True,
            mmr_push_enabled=True,
            outbound_base_url="https://other.example",
            outbound_auth="none",
            outbound_authorizer=self.owner,
        )
        set_org_mmr(
            self.member,
            self.game,
            4000,
            mark_verified=False,
            sync_context=MmrMutationContext(origin_connection_id=self.connection.pk),
        )
        self.assertEqual(
            list(OrgApiMmrDelivery.objects.values_list("connection_id", flat=True)),
            [other.pk],
        )
        self.assertEqual(self.state().last_source_connection_id, self.connection.pk)

    def test_expected_revision_conflict_preserves_value(self) -> None:
        self.write(4500)
        with self.assertRaises(MmrRevisionConflict):
            set_org_mmr(
                self.member,
                self.game,
                5000,
                mark_verified=False,
                sync_context=MmrMutationContext(expected_revision=0),
            )
        self.assertEqual(self.state().value, 4500)

    def test_inbound_optional_revision_and_legacy_shape(self) -> None:
        self.write(4500)
        result = sync_mmrs(
            self.org,
            self.owner,
            [{"steam_id": 12345, "mmr": 5000, "expected_revision": 0}],
            mark_verified=False,
        )
        self.assertEqual(result.updated, 0)
        self.assertEqual(self.state().value, 4500)
        self.assertEqual(result.invalid[0]["error"], "conflict")
        self.assertEqual(
            set(result.as_dict()), {"updated", "unchanged", "unmatched", "invalid"}
        )
        self.assertEqual(
            member_rows(self.org, self.game)[0]["revision"], self.state().revision
        )

    def test_identity_only_user_changes_publish_current_value(self) -> None:
        self.write(4500)
        for field, value in (
            ("steam_account_id", 22222),
            ("discordId", "987654321012345679"),
        ):
            with self.subTest(field=field):
                before = self.state().revision
                setattr(self.user, field, value)
                self.user.save(update_fields=[field])
                self.assertGreater(self.state().revision, before)
                entry = (
                    OrgApiMmrDelivery.objects.filter(game_type=self.game)
                    .latest("pk")
                    .payload["entries"][0]
                )
                self.assertEqual(entry["steam_id"], str(self.user.steam_account_id))
                self.assertEqual(entry["discord_id"], self.user.discordId)
                self.assertEqual(entry["mmr"], 4500)

    def test_claim_membership_reassignment_publishes_once(self) -> None:
        self.write(4500)
        before = self.state().revision
        self.member.user = self.owner
        self.member.save(update_fields=["user"])
        self.assertGreater(self.state().revision, before)
        self.assertEqual(
            OrgApiMmrDelivery.objects.filter(game_type=self.game).count(), 2
        )
        self.assertIsNone(
            OrgApiMmrDelivery.objects.latest("pk").payload["entries"][0]["steam_id"]
        )

    def test_merge_and_rejoin_never_reuse_revision(self) -> None:
        self.write(4500)
        first = self.state().revision
        loser_user = CustomUser.objects.create_user(username="mutation-loser")
        loser = OrgUser.objects.create(organization=self.org, user=loser_user)
        set_org_mmr(loser, self.game, 5000, mark_verified=False)
        loser_revision = self.state(loser).revision
        merge_org_mmrs(loser, self.member)
        self.assertGreater(self.state().revision, loser_revision)
        self.member.delete()
        self.assertFalse(
            OrgApiMmrDelivery.objects.filter(state="pending", org_user=None).exists()
        )
        self.member = OrgUser.objects.create(organization=self.org, user=self.user)
        self.write(4500)
        self.assertGreater(self.state().revision, first)
        self.assertGreater(self.state().revision, loser_revision)

    def test_authority_lost_or_feature_locked_never_enqueues(self) -> None:
        self.owner.is_active = False
        self.owner.save(update_fields=["is_active"])
        self.write(4000)
        self.assertFalse(OrgApiMmrDelivery.objects.exists())
        self.owner.is_active = True
        self.owner.save(update_fields=["is_active"])
        set_org_feature(self.org, FeatureKey.MMR_SYNC, enabled=False, actor=None)
        self.write(4500)
        self.assertFalse(OrgApiMmrDelivery.objects.exists())

    def test_deleted_membership_cannot_be_written_by_stale_instance(self) -> None:
        stale = OrgUser.objects.get(pk=self.member.pk)
        self.member.delete()
        with self.assertRaises(OrgUser.DoesNotExist):
            set_org_mmr(stale, self.game, 4000, mark_verified=False)

    def test_mutation_path_inventory_csv_endpoints(self) -> None:
        client = APIClient()
        client.force_authenticate(self.owner)
        league = League.objects.create(name="Mutation League", organization=self.org)
        tournament = Tournament.objects.create(
            name="Mutation Cup", league=league, date_played=timezone.now()
        )
        for path, value in (
            (f"/api/organizations/{self.org.pk}/import-csv/", 4000),
            (f"/api/tournaments/{tournament.pk}/import-csv/", 5000),
        ):
            with self.subTest(path=path):
                response = client.post(
                    path,
                    {
                        "rows": [
                            {"steam_friend_id": str(self.user.steamid), "mmr": value}
                        ],
                        "update_mmr": True,
                    },
                    format="json",
                )
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(self.state().value, value)
                self.assertEqual(
                    OrgApiMmrDelivery.objects.filter(game_type=self.game)
                    .latest("pk")
                    .payload["entries"][0]["mmr"],
                    value,
                )

    def test_mutation_path_inventory_import_command(self) -> None:
        command = Command()
        command.new_user_mmrs = {self.user.pk: 4200}
        command._write_org_mmrs(self.org, self.game)
        self.assertEqual(self.state().value, 4200)
        self.assertEqual(OrgApiMmrDelivery.objects.count(), 1)

    def test_mutation_path_inventory_discord_merge(self) -> None:
        self.write(4500)
        keeper = CustomUser.objects.create_user(
            username="identity-keeper", discordId="987654321012345680"
        )
        keeper_member = OrgUser.objects.create(organization=self.org, user=keeper)
        set_org_mmr(keeper_member, self.game, 4500, mark_verified=False)
        before = self.state(keeper_member).revision
        count = OrgApiMmrDelivery.objects.filter(
            org_user=keeper_member, game_type=self.game
        ).count()
        merge_discord_accounts(keeper, self.user)
        self.assertEqual(
            OrgApiMmrDelivery.objects.filter(
                org_user=keeper_member, game_type=self.game
            ).count(),
            count + 1,
        )
        self.assertGreater(self.state(keeper_member).revision, before)
        delivery = OrgApiMmrDelivery.objects.filter(
            org_user=keeper_member, game_type=self.game
        ).latest("pk")
        self.assertEqual(delivery.payload["entries"][0]["steam_id"], "12345")
        self.assertEqual(delivery.payload["entries"][0]["discord_id"], keeper.discordId)
        self.assertEqual(delivery.payload["entries"][0]["mmr"], 4500)

    def test_mutation_path_inventory_claim_endpoint(self) -> None:
        self.user.discordId = None
        self.user.save(update_fields=["discordId"])
        self.write(4500)
        before = self.state().revision
        claimer = CustomUser.objects.create_user(
            username="claim-player", discordId="987654321012345680"
        )
        self.org.admins.add(self.owner)
        claim = ProfileClaimRequest.objects.create(
            organization=self.org, target_user=self.user, claimer=claimer
        )
        client = APIClient()
        client.force_authenticate(self.owner)
        response = client.post(f"/api/claim-requests/{claim.pk}/approve/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertGreater(self.state().revision, before)
        delivery = OrgApiMmrDelivery.objects.filter(
            org_user=self.member, game_type=self.game
        ).latest("pk")
        self.assertEqual(delivery.payload["entries"][0]["steam_id"], "12345")
        self.assertEqual(
            delivery.payload["entries"][0]["discord_id"], claimer.discordId
        )

    def test_mutation_path_inventory_verifier_reassignment(self) -> None:
        verifier = CustomUser.objects.create_user(username="old-verifier")
        set_org_mmr(
            self.member, self.game, 4500, mark_verified=True, verified_by=verifier
        )
        before = self.state().revision
        count = OrgApiMmrDelivery.objects.count()
        repoint_mmr_requests(self.owner, verifier, [], [])
        self.assertGreater(self.state().revision, before)
        self.assertEqual(OrgApiMmrDelivery.objects.count(), count)

    def test_mutation_path_inventory_league_excluded(self) -> None:
        league = League.objects.create(name="Excluded League", organization=self.org)
        member = LeagueUser.objects.create(
            league=league, user=self.user, org_user=self.member
        )
        set_league_mmr(member, 4000, actor=self.owner, verified=False, source="test")
        self.assertFalse(OrgMmrSyncState.objects.exists())
        self.assertFalse(OrgApiMmrDelivery.objects.exists())

    def test_zero_official_set_and_identity_preserve_verification(self) -> None:
        set_org_mmr(
            self.member, self.game, 0, mark_verified=True, verified_by=self.owner
        )
        verified_at = self.state().verified_at
        self.assertIsNotNone(verified_at)
        self.user.discordId = "987654321012345681"
        self.user.save(update_fields=["discordId"])
        self.assertEqual(self.state().verified_at, verified_at)
        before = self.state().revision
        bulk_set_org_mmrs(self.org.pk, self.game, {self.user.pk: 0})
        self.assertGreater(self.state().revision, before)
        self.assertIsNone(self.state().verified_at)

    @override_settings(STEAM_ACCOUNT_LOOKUP_ENABLED=False)
    def test_mutation_path_inventory_profile_and_global_admin_api(self) -> None:
        self.write(4500)
        client = APIClient()
        client.force_authenticate(self.user)
        before = self.state().revision
        response = client.post(
            "/api/profile_update", {"steam_account_id": 33333}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertGreater(self.state().revision, before)
        client.force_authenticate(self.owner)
        before = self.state().revision
        response = client.patch(
            f"/api/users/{self.user.pk}/", {"steam_account_id": 44444}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertGreater(self.state().revision, before)
        entry = (
            OrgApiMmrDelivery.objects.filter(game_type=self.game)
            .latest("pk")
            .payload["entries"][0]
        )
        self.assertEqual(entry["steam_id"], "44444")

    def test_mutation_path_inventory_django_admin_save(self) -> None:
        self.write(4500)
        before = self.state().revision
        self.user.discordId = "987654321012345682"
        request = RequestFactory().post("/admin/app/customuser/")
        request.user = self.owner
        CustomUserAdmin(CustomUser, admin.site).save_model(
            request, self.user, None, True
        )
        self.assertGreater(self.state().revision, before)
        self.assertEqual(
            OrgApiMmrDelivery.objects.filter(game_type=self.game)
            .latest("pk")
            .payload["entries"][0]["discord_id"],
            self.user.discordId,
        )

    def test_mutation_path_inventory_discord_linking(self) -> None:
        self.write(4500)
        before = self.state().revision
        UserSocialAuth.objects.create(
            user=self.user,
            provider="discord",
            uid="987654321012345683",
            extra_data={
                "id": "987654321012345683",
                "avatar": "synthetic",
                "username": self.user.username,
            },
        )
        save_discord(None, None, self.user)
        self.assertGreater(self.state().revision, before)
        self.assertEqual(
            OrgApiMmrDelivery.objects.filter(game_type=self.game)
            .latest("pk")
            .payload["entries"][0]["discord_id"],
            "987654321012345683",
        )

    def test_excluded_identity_field_is_still_tracked_on_later_save(self) -> None:
        self.write(4500)
        self.user.discordId = "987654321012345684"
        self.user.save(update_fields=["username"])
        before = self.state().revision
        self.user.save(update_fields=["discordId"])
        self.assertGreater(self.state().revision, before)

    def test_stale_unrelated_user_save_preserves_current_identifiers(self) -> None:
        self.write(4500)
        stale = CustomUser.objects.get(pk=self.user.pk)
        self.user.discordId = "987654321012345685"
        self.user.save(update_fields=["discordId"])
        before = self.state().revision
        stale.username = "renamed-player"
        stale.save()
        self.user.refresh_from_db()
        self.assertEqual(self.user.discordId, "987654321012345685")
        self.assertEqual(self.state().revision, before)

    def test_explicit_stale_user_save_still_revisions_actual_identity_change(
        self,
    ) -> None:
        self.write(4500)
        stale = CustomUser.objects.get(pk=self.user.pk)
        self.user.discordId = "987654321012345685"
        self.user.save(update_fields=["discordId"])
        before = self.state().revision
        stale.save(update_fields=["discordId"])
        self.assertGreater(self.state().revision, before)

    def test_sync_context_revision_is_not_dropped_when_entry_omits_it(self) -> None:
        self.write(4500)
        result = sync_mmrs(
            self.org,
            self.owner,
            [{"steam_id": 12345, "mmr": 5000}],
            mark_verified=False,
            sync_context=MmrMutationContext(expected_revision=0),
        )
        self.assertEqual(result.updated, 0)
        self.assertEqual(result.invalid[0]["error"], "conflict")
        self.assertEqual(self.state().value, 4500)

    def test_explicit_stale_membership_save_revisions_user_reassignment(self) -> None:
        self.write(4500)
        stale = OrgUser.objects.get(pk=self.member.pk)
        self.member.user = self.owner
        self.member.save(update_fields=["user"])
        before = self.state().revision
        stale.save(update_fields=["user"])
        self.assertGreater(self.state().revision, before)
        self.member.refresh_from_db()
        self.assertEqual(self.member.user_id, self.user.pk)

    def test_stale_unrelated_membership_save_preserves_current_user(self) -> None:
        self.write(4500)
        stale = OrgUser.objects.get(pk=self.member.pk)
        self.member.user = self.owner
        self.member.save(update_fields=["user"])
        before = self.state().revision
        stale.guild_nickname = "Synthetic nickname"
        stale.save()
        self.member.refresh_from_db()
        self.assertEqual(self.member.user_id, self.owner.pk)
        self.assertEqual(self.state().revision, before)

    def test_excluded_membership_identity_is_tracked_on_later_save(self) -> None:
        self.write(4500)
        self.member.user = self.owner
        self.member.save(update_fields=["guild_nickname"])
        before = self.state().revision
        self.member.save(update_fields=["user"])
        self.assertGreater(self.state().revision, before)

    def test_official_writer_drops_callers_prefetch_and_memo(self) -> None:
        self.write(4500)
        caller = OrgUser.objects.prefetch_related(game_mmrs_prefetch(fresh=True)).get(
            pk=self.member.pk
        )
        self.assertEqual(get_org_mmr(caller, self.game), 4500)
        apply_official_org_mmr(caller, self.game, 5000, actor=self.owner, source="test")
        self.assertNotIn("game_mmrs", getattr(caller, "_prefetched_objects_cache", {}))
        self.assertTrue(caller.has_active_dota_mmr)
        fresh = OrgUser.objects.prefetch_related(game_mmrs_prefetch(fresh=True)).get(
            pk=caller.pk
        )
        self.assertEqual(get_org_mmr(fresh, self.game), 5000)

    def test_zero_verification_changes_revision_and_no_push(self) -> None:
        mark_org_mmr_verified(self.member, self.game, self.owner)
        first = self.state().revision
        mark_org_mmr_verified(self.member, self.game, self.owner)
        self.assertGreater(self.state().revision, first)
        self.assertIsNotNone(self.state().verified_at)
        self.assertFalse(OrgApiMmrDelivery.objects.exists())

    def test_unverified_sync_of_unchanged_value_keeps_verification(self) -> None:
        set_org_mmr(
            self.member, self.game, 4500, mark_verified=True, verified_by=self.owner
        )
        before = self.state()
        result = sync_mmrs(
            self.org,
            self.owner,
            [{"steam_id": 12345, "mmr": 4500}],
            mark_verified=False,
        )
        self.assertEqual((result.updated, result.unchanged), (0, 1))
        after = self.state()
        self.assertEqual(after.revision, before.revision)
        self.assertEqual(after.verified_at, before.verified_at)
        row = OrgUserGameMmr.objects.get(org_user=self.member, game_type=self.game)
        self.assertIsNotNone(row.verified_at)
        self.assertEqual(row.verified_by_id, self.owner.pk)

    def test_identity_change_skips_games_without_a_value(self) -> None:
        self.write(4500)
        self.user.discordId = "987654321012345686"
        self.user.save(update_fields=["discordId"])
        self.assertEqual(
            set(OrgMmrSyncState.objects.values_list("game_type", flat=True)),
            {self.game},
        )
        self.assertEqual(
            set(OrgApiMmrDelivery.objects.values_list("game_type", flat=True)),
            {self.game},
        )
        self.assertFalse(
            OrgApiMmrDelivery.objects.exclude(game_type=self.game).exists()
        )

    def test_stale_verification_save_preserves_newer_discord_id(self) -> None:
        self.write(4500)
        stale = CustomUser.objects.get(pk=self.user.pk)
        self.user.discordId = "987654321012345688"
        self.user.save(update_fields=["discordId"])
        before = self.state().revision
        stale.steam_account_exists_checked_at = timezone.now()
        stale.save()
        self.user.refresh_from_db()
        self.assertEqual(self.user.discordId, "987654321012345688")
        self.assertIsNotNone(self.user.steam_account_exists_checked_at)
        self.assertEqual(self.state().revision, before)

    def test_deleting_verifier_records_verification_revision(self) -> None:
        verifier = CustomUser.objects.create_user(username="deleted-verifier")
        set_org_mmr(
            self.member, self.game, 4500, mark_verified=True, verified_by=verifier
        )
        before = self.state().revision
        count = OrgApiMmrDelivery.objects.count()
        admin_user = CustomUser.objects.create_superuser(
            username="verifier-delete-admin", password="synthetic"
        )
        client = APIClient()
        client.force_authenticate(admin_user)
        response = client.delete(f"/api/users/{verifier.pk}/")
        self.assertEqual(response.status_code, 204)
        row = OrgUserGameMmr.objects.get(org_user=self.member, game_type=self.game)
        self.assertIsNone(row.verified_by_id)
        self.assertIsNotNone(row.verified_at)
        self.assertGreater(self.state().revision, before)
        self.assertEqual(OrgApiMmrDelivery.objects.count(), count)

    def test_batched_identity_change_allocates_one_revision(self) -> None:
        self.write(4500)
        keeper = CustomUser.objects.create_user(
            username="batch-keeper", discordId="987654321012345689"
        )
        keeper_member = OrgUser.objects.create(organization=self.org, user=keeper)
        set_org_mmr(keeper_member, self.game, 4500, mark_verified=False)
        counter = OrgMmrRevisionCounter.objects.get(
            organization=self.org, game_type=self.game
        ).revision
        merge_discord_accounts(keeper, self.user)
        self.assertEqual(self.state(keeper_member).revision, counter + 1)
        self.assertEqual(
            OrgMmrRevisionCounter.objects.get(
                organization=self.org, game_type=self.game
            ).revision,
            counter + 1,
        )

    def test_admin_deleting_verifier_records_verification_revision(self) -> None:
        verifier = CustomUser.objects.create_user(username="admin-deleted-verifier")
        set_org_mmr(
            self.member, self.game, 4500, mark_verified=True, verified_by=verifier
        )
        before = self.state().revision
        request = RequestFactory().post("/admin/app/customuser/")
        request.user = self.owner
        CustomUserAdmin(CustomUser, admin.site).delete_queryset(
            request, CustomUser.objects.filter(pk=verifier.pk)
        )
        row = OrgUserGameMmr.objects.get(org_user=self.member, game_type=self.game)
        self.assertIsNone(row.verified_by_id)
        self.assertGreater(self.state().revision, before)
