from datetime import UTC, date, datetime
from typing import Any

from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from django_test_migrations.contrib.unittest_case import MigratorTestCase
from rest_framework.test import APIClient

from org.api_tokens.tokens import hash_secret
from org.integration.receipts import format_timestamp
from org.tests.test_api_tokens import LOCMEM_CACHE
from org.tests.test_integration_contacts import GUILD, bindings

BEFORE = ("org", "0030_promotion_observations_and_keys")
AFTER = ("org", "0033_api_connection_constraints")
AT = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
MMR_PAIR = ["mmr:read", "mmr:write"]


class ConnectionBackfillMigrationTest(MigratorTestCase):
    migrate_from = BEFORE
    migrate_to = AFTER

    def prepare(self) -> None:
        apps = self.old_state.apps
        CustomUser = apps.get_model("app", "CustomUser")
        Organization = apps.get_model("org", "Organization")
        OrgUser = apps.get_model("org", "OrgUser")
        GameMmr = apps.get_model("org", "OrgUserGameMmr")
        Token = apps.get_model("org", "OrgApiToken")
        Usage = apps.get_model("org", "OrgApiTokenUsage")

        owner = CustomUser.objects.create(username="backfill_owner")
        other = CustomUser.objects.create(username="backfill_other")
        Feature = apps.get_model("org", "OrgFeature")
        verifier = CustomUser.objects.create(username="backfill_verifier")
        org = Organization.objects.create(
            name="Backfill org", owner=owner, discord_server_id=GUILD
        )
        org.admins.add(owner, other)
        Feature.objects.create(organization=org, feature="promotion", enabled=True)
        self.org = org.pk
        self.org_two = Organization.objects.create(name="Second org", owner=owner).pk
        ou_owner = OrgUser.objects.create(user=owner, organization_id=self.org)
        ou_other = OrgUser.objects.create(user=other, organization_id=self.org)
        GameMmr.objects.create(org_user=ou_owner, game_type=1, mmr=4200)
        GameMmr.objects.create(
            org_user=ou_other,
            game_type=1,
            mmr=3100,
            verified_at=AT,
            verified_by=verifier,
        )
        GameMmr.objects.create(org_user=ou_other, game_type=2, mmr=0)

        def token(name: str, operations: list[str], **kwargs: Any) -> int:
            return Token.objects.create(
                organization_id=kwargs.pop("org", self.org),
                user=kwargs.pop("user", owner),
                name=name,
                prefix=f"bf{name}",
                secret_hash=hash_secret(f"secret{name}"),
                operations=operations,
                **kwargs,
            ).pk

        self.import_a = token("importa", ["promotion:import"])
        self.import_b = token("importb", ["mmr:read", "promotion:import"], user=other)
        self.import_revoked = token(
            "importc", ["promotion:import"], revoked_at=AT, revoked_by=owner
        )
        self.mmr_a = token("mmra", MMR_PAIR)
        self.mmr_b = token("mmrb", ["mmr:read"], revoked_at=AT)
        self.other_org_import = token(
            "otherimport", ["promotion:import"], org=self.org_two
        )
        Usage.objects.create(
            token_id=self.import_a,
            organization_id=self.org,
            user=owner,
            date=date(2026, 11, 25),
            request_count=7,
            throttled_count=1,
        )
        self.tokens_before = {
            row["pk"]: row
            for row in Token.objects.values(
                "pk",
                "organization_id",
                "user_id",
                "name",
                "prefix",
                "secret_hash",
                "operations",
                "revoked_at",
                "revoked_by_id",
            )
        }

    def test_backfill_shared_import_stream_preserves_all_credentials(self) -> None:
        apps = self.new_state.apps
        Token = apps.get_model("org", "OrgApiToken")
        Usage = apps.get_model("org", "OrgApiTokenUsage")
        Connection = apps.get_model("org", "OrgApiConnection")

        tokens = {t.pk: t for t in Token.objects.all()}
        for pk, before in self.tokens_before.items():
            after = Token.objects.filter(pk=pk).values(*before).get()
            self.assertEqual(after, before)
            self.assertIsNotNone(tokens[pk].connection_id)

        stream = tokens[self.import_a].connection
        self.assertEqual(tokens[self.import_b].connection_id, stream.pk)
        self.assertEqual(tokens[self.import_revoked].connection_id, stream.pk)
        self.assertTrue(stream.legacy_multi_credential)
        self.assertTrue(stream.legacy_backfilled)
        self.assertTrue(stream.enabled)
        self.assertTrue(stream.inbound_enabled)
        for flag in ("mmr_push_enabled", "mmr_pull_enabled", "promotion_push_enabled"):
            self.assertFalse(getattr(stream, flag))
        self.assertEqual(stream.operations, ["mmr:read", "promotion:import"])
        self.assertTrue(all(tokens[pk].legacy_credential for pk in self.tokens_before))

        self.assertNotEqual(tokens[self.mmr_a].connection_id, stream.pk)
        self.assertNotEqual(
            tokens[self.mmr_a].connection_id, tokens[self.mmr_b].connection_id
        )
        mmr_connection = tokens[self.mmr_a].connection
        self.assertEqual(mmr_connection.name, "mmra")
        self.assertEqual(mmr_connection.operations, MMR_PAIR)
        self.assertEqual(mmr_connection.created_by_id, tokens[self.mmr_a].user_id)
        self.assertFalse(mmr_connection.legacy_multi_credential)
        self.assertNotEqual(
            tokens[self.other_org_import].connection.organization_id, self.org
        )
        self.assertEqual(Connection.objects.filter(organization_id=self.org).count(), 3)
        self.assertEqual(
            list(
                Usage.objects.values_list(
                    "token_id", "request_count", "throttled_count"
                )
            ),
            [(self.import_a, 7, 1)],
        )
        for model in (
            "OrgApiPromotionAdoption",
            "OrgApiPromotionBinding",
            "OrgApiMmrDelivery",
            "OrgApiSyncRun",
        ):
            self.assertFalse(apps.get_model("org", model).objects.exists(), model)
        self.assertFalse(
            Connection.objects.exclude(outbound_credential_ciphertext="").exists()
        )

    def test_backfill_seeds_sync_state_at_revision_zero(self) -> None:
        apps = self.new_state.apps
        State = apps.get_model("org", "OrgMmrSyncState")
        Counter = apps.get_model("org", "OrgMmrRevisionCounter")
        states = sorted(
            State.objects.values_list(
                "org_user__user__username",
                "game_type",
                "revision",
                "value",
                "verified_at",
            )
        )
        self.assertEqual(
            states,
            [
                ("backfill_other", 1, 0, 3100, AT),
                ("backfill_other", 2, 0, 0, None),
                ("backfill_owner", 1, 0, 4200, None),
            ],
        )
        self.assertEqual(
            sorted(
                Counter.objects.values_list("organization_id", "game_type", "revision")
            ),
            [(self.org, 1, 0), (self.org, 2, 0)],
        )

    def test_backfilled_tokens_still_authenticate_and_import(self) -> None:
        self._migrator.apply_tested_migration(
            ("org", "0035_api_connection_key_version")
        )
        cache.clear()
        url = f"/api/organizations/{self.org}/integration/v1/contact-receipts/"
        Organization = self.new_state.apps.get_model("org", "Organization")
        config = bindings(Organization.objects.get(pk=self.org), {})
        with override_settings(CACHES=LOCMEM_CACHE, PROMOTION_SYNC=config):
            for through, name in enumerate(("importa", "importb"), start=1):
                client = APIClient()
                client.credentials(
                    HTTP_AUTHORIZATION=f"Bearer dfk_bf{name}_secret{name}"
                )
                resp = client.post(
                    url,
                    {
                        "source": "contact_log",
                        "guild_id": GUILD,
                        "scan_started_at": format_timestamp(timezone.now()),
                        "range": {"after": str(through - 1), "through": str(through)},
                        "skipped_ids": [str(through)],
                        "entries": [],
                    },
                    format="json",
                )
                self.assertEqual(resp.status_code, 200, resp.content)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION="Bearer dfk_bfimportc_secretimportc")
            self.assertEqual(client.post(url, {}, format="json").status_code, 401)
