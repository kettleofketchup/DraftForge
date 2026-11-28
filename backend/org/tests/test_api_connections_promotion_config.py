import io
import json
import tempfile
from dataclasses import replace
from datetime import datetime, timedelta
from unittest.mock import patch

from django.conf import settings
from django.core.management import CommandError, call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIClient

from app.models import CustomUser
from config.promotion_sync import PromotionSyncConfig
from events.models import Event
from org.api_connections import tls_adapter
from org.api_connections.crypto import canonical_origin, open_credential
from org.api_connections.promotion_config import (
    LEGACY_EFFECTIVE_AT,
    PromotionStreamError,
    adopt_legacy_promotion,
    env_dispatch_bindings,
    resolve_promotion_config,
)
from org.api_tokens.tokens import hash_secret
from org.integration.bindings import get_event_binding, get_org_binding
from org.integration.contacts import ImportBatch, contact_sync_status
from org.integration.errors import IntegrationError
from org.integration.observations import record_ranges
from org.models import (
    OrgApiConnection,
    OrgApiPromotionAdoption,
    OrgApiPromotionBinding,
    OrgApiPromotionEventBinding,
    OrgApiToken,
    OrgLog,
)
from org.models_promotion_sync import (
    ExternalPromotionReceipt,
    OutboxState,
    PromotionImportObservation,
)
from org.tests.test_api_connections_crypto import OLD_KEY
from org.tests.test_integration_contacts import GUILD, OCCASION, _ImportBase
from org.tests.test_promotion_dispatch import FakeClient, _DispatchFixture, applied

PUBLIC = "93.184.216.34"
BASE_URL = "https://adaptor.example"
PER_ORG_KEY = "per-org-adaptor-key"


@override_settings(ORG_API_CREDENTIAL_KEYS=json.dumps([OLD_KEY]))
class _AdoptionBase(_ImportBase):
    def setUp(self) -> None:
        super().setUp()
        self.operator = CustomUser.objects.create_superuser(
            username="promo-operator", password="x"
        )
        resolve = patch.object(tls_adapter, "_resolve", return_value=(PUBLIC,))
        self.resolve = resolve.start()
        self.addCleanup(resolve.stop)

    def adopt(self, **overrides: object) -> OrgApiConnection:
        values: dict[str, object] = {
            "org_id": self.org.pk,
            "actor": self.operator,
            "credential": PER_ORG_KEY,
            "base_url": BASE_URL,
            "dry_run": False,
        }
        values.update(overrides)
        return adopt_legacy_promotion(**values)  # type: ignore[arg-type]

    def assertAdoptionError(self, code: str, **overrides: object) -> None:
        with self.assertRaises(PromotionStreamError) as caught:
            self.adopt(**overrides)
        self.assertEqual(caught.exception.code, code)
        self.assertFalse(OrgApiPromotionAdoption.objects.exists())
        self.assertFalse(OrgApiPromotionBinding.objects.exists())


class PromotionResolverTests(_AdoptionBase):
    def test_unadopted_org_uses_deployment_config(self) -> None:
        resolved = resolve_promotion_config(self.org.pk)
        self.assertEqual(resolved.source, "deployment")
        self.assertFalse(resolved.adopted)
        self.assertEqual(resolved.events[self.event.pk], OCCASION)
        self.assertEqual(resolved.transport, "none")
        none = resolve_promotion_config(self.other_org.pk)
        self.assertEqual((none.source, none.binding), ("none", None))

    def test_operator_adoption_requires_per_org_key_and_public_origin(self) -> None:
        staff = CustomUser.objects.create_user(username="staffer", is_staff=True)
        self.assertAdoptionError("operator_required", actor=staff)
        self.assertAdoptionError("operator_required", actor=self.admin)
        self.assertAdoptionError("invalid_credential", credential="")
        self.assertAdoptionError("invalid_credential", credential="dfk_abc_def")
        self.assertAdoptionError("invalid_credential", credential="has space")
        for url in (
            "http://adaptor.example",
            "https://adaptor.example:8443",
            "https://127.0.0.1",
            "https://adaptor.example/path?x=1",
        ):
            self.assertAdoptionError("unsafe_destination", base_url=url)
        self.resolve.return_value = (PUBLIC, "10.0.0.5")
        self.assertAdoptionError("unsafe_destination")
        self.resolve.return_value = (PUBLIC,)
        self.assertAdoptionError("not_legacy_bound", org_id=self.other_org.pk)

        connection = self.adopt()
        self.assertEqual(connection.pk, self.issued.token.connection_id)
        self.assertEqual(connection.outbound_credential_owner, self.operator)
        self.assertEqual(connection.outbound_auth, "bearer")
        self.assertFalse(connection.promotion_push_enabled)
        self.assertEqual(
            canonical_origin(connection.outbound_base_url), BASE_URL + ":443"
        )
        adoption = OrgApiPromotionAdoption.objects.get(organization=self.org)
        self.assertEqual(
            (adoption.connection_id, adoption.adopted_by_id),
            (connection.pk, self.operator.pk),
        )
        events = {
            row.event_id: (row.occasion_id, row.effective_at)
            for row in OrgApiPromotionEventBinding.objects.all()
        }
        self.assertEqual(events[self.event.pk], (OCCASION, LEGACY_EFFECTIVE_AT))
        self.assertTrue(OrgLog.objects.filter(action="adopt_promotion_sync").exists())
        with self.assertRaises(PromotionStreamError) as again:
            self.adopt()
        self.assertEqual(again.exception.code, "promotion_stream_exists")
        self.assertEqual(OrgApiPromotionAdoption.objects.count(), 1)

    def test_dry_run_reports_new_connection_without_pk(self) -> None:
        OrgApiConnection.objects.filter(pk=self.issued.token.connection_id).update(
            archived_at=timezone.now()
        )
        before = OrgApiConnection.objects.count()
        connection = self.adopt(dry_run=True)
        self.assertIsNone(connection.pk)
        self.assertEqual(OrgApiConnection.objects.count(), before)

    def test_adoption_refuses_connection_with_other_destination(self) -> None:
        OrgApiConnection.objects.filter(pk=self.issued.token.connection_id).update(
            outbound_base_url="https://mmr.example"
        )
        self.assertAdoptionError("destination_conflict")
        OrgApiConnection.objects.filter(pk=self.issued.token.connection_id).update(
            outbound_base_url=BASE_URL
        )
        self.assertEqual(self.adopt().pk, self.issued.token.connection_id)

    def test_adopted_stream_is_sole_promotion_authority(self) -> None:
        stray = OrgApiConnection.objects.create(
            organization=self.org,
            name="stray",
            enabled=True,
            inbound_enabled=True,
            operations=["promotion:import"],
        )
        connection = self.adopt()
        self.assertEqual(connection.pk, self.issued.token.connection_id)
        self.assertNotEqual(stray.pk, connection.pk)
        raw = "dfk_0123456789ab_stray-secret"
        OrgApiToken.objects.create(
            connection=stray,
            organization=self.org,
            user=self.admin,
            issued_by=self.admin,
            name="stray",
            prefix="0123456789ab",
            secret_hash=hash_secret("stray-secret"),
            operations=["promotion:import"],
        )
        resp = self.post([self.entry(8022, self.recipient)], raw=raw)
        self.assertError(resp, 403, "operation_not_granted")
        self.imported([self.entry(8022, self.recipient)])
        session = APIClient()
        session.force_authenticate(self.admin)
        legacy = session.post(
            f"/api/organizations/{self.org.pk}/api-tokens/",
            {"name": "late", "operations": ["promotion:import"]},
            format="json",
        )
        self.assertEqual(legacy.status_code, 409, legacy.data)
        self.assertEqual(legacy.data["code"], "promotion_stream_exists")

    def test_legacy_key_issued_before_adoption_keeps_working(self) -> None:
        session = APIClient()
        session.force_authenticate(self.admin)
        late = session.post(
            f"/api/organizations/{self.org.pk}/api-tokens/",
            {"name": "late", "operations": ["promotion:read", "promotion:import"]},
            format="json",
        )
        self.assertEqual(late.status_code, 201, late.data)
        token = OrgApiToken.objects.get(pk=late.data["id"])
        self.assertEqual(token.connection_id, self.issued.token.connection_id)
        self.assertTrue(token.legacy_credential)
        self.assertEqual(token.operations, ["promotion:import", "promotion:read"])
        stream = OrgApiConnection.objects.get(pk=token.connection_id)
        self.assertEqual(stream.operations, ["promotion:import", "promotion:read"])
        self.imported([self.entry(8021, self.recipient)], raw=late.data["token"])
        self.assertEqual(self.adopt().pk, stream.pk)
        self.imported(
            [self.entry(8022, self.recipient)],
            raw=late.data["token"],
            after=8021,
            through=8022,
        )

    def test_legacy_key_refused_beside_single_credential_stream(self) -> None:
        OrgApiConnection.objects.filter(pk=self.issued.token.connection_id).update(
            legacy_multi_credential=False
        )
        before = OrgApiConnection.objects.count()
        session = APIClient()
        session.force_authenticate(self.admin)
        resp = session.post(
            f"/api/organizations/{self.org.pk}/api-tokens/",
            {"name": "late", "operations": ["promotion:import"]},
            format="json",
        )
        self.assertEqual(resp.status_code, 409, resp.data)
        self.assertEqual(resp.data["code"], "promotion_stream_exists")
        self.assertEqual(OrgApiConnection.objects.count(), before)

    def test_adoption_refuses_promotion_keys_off_stream(self) -> None:
        stray = OrgApiConnection.objects.create(
            organization=self.org,
            name="stray",
            enabled=True,
            inbound_enabled=True,
            operations=["promotion:import"],
        )
        OrgApiToken.objects.create(
            connection=stray,
            organization=self.org,
            user=self.admin,
            issued_by=self.admin,
            name="stray",
            prefix="0123456789ab",
            secret_hash="0" * 64,
            operations=["promotion:import"],
        )
        self.assertAdoptionError("promotion_keys_elsewhere", dry_run=True)
        self.assertAdoptionError("promotion_keys_elsewhere")
        OrgApiToken.objects.filter(connection=stray).update(revoked_at=timezone.now())
        self.assertEqual(self.adopt().pk, self.issued.token.connection_id)

    def test_dry_run_writes_nothing(self) -> None:
        connection = self.adopt(dry_run=True)
        self.assertIsNotNone(connection.pk)
        self.assertFalse(OrgApiPromotionAdoption.objects.exists())
        self.assertFalse(OrgApiPromotionBinding.objects.exists())
        connection.refresh_from_db()
        self.assertEqual(connection.outbound_credential_ciphertext, "")
        self.assertEqual(resolve_promotion_config(self.org.pk).source, "deployment")

    def test_guild_mismatch_and_foreign_events_block_adoption(self) -> None:
        self.org.discord_server_id = "770000000000000099"
        self.org.save()
        self.assertAdoptionError("binding_mismatch")
        self.org.discord_server_id = GUILD
        self.org.save()
        foreign = self.event.__class__.objects.create(
            organization=self.other_org,
            name="Foreign",
            scheduled_at=self.event.scheduled_at,
            created_by=self.admin,
        )
        self.bind({self.event: OCCASION, foreign: 4321})
        self.assertAdoptionError("foreign_event")

    def test_env_key_never_copied(self) -> None:
        shared = replace(
            settings.PROMOTION_ADAPTOR, enabled=True, api_key="shared-env-key"
        )
        with override_settings(PROMOTION_ADAPTOR=shared):
            self.assertAdoptionError("shared_credential", credential="shared-env-key")
            connection = self.adopt()
        stored = connection.outbound_credential_ciphertext
        self.assertNotIn("shared-env-key", stored)
        self.assertNotIn(PER_ORG_KEY, stored)
        self.assertEqual(
            open_credential(
                stored,
                org_id=self.org.pk,
                connection_id=connection.pk,
                origin=canonical_origin(connection.outbound_base_url),
            ),
            PER_ORG_KEY,
        )

    def test_adoption_preserves_source_ids_revision_and_scan_cursor(self) -> None:
        self.imported(
            [self.entry(8021, self.recipient), self.entry(8022, self.recipient)]
        )
        self.imported(
            [self.entry(8021, self.recipient, contact_method="DISCORD_GROUP_DM")],
            after=8020,
            through=8022,
            skipped=[8022],
        )
        before = list(
            ExternalPromotionReceipt.objects.order_by("pk").values(
                "pk",
                "source_contact_id",
                "source_revision",
                "source_hash",
                "connection",
            )
        )
        spans = list(
            PromotionImportObservation.objects.order_by("after").values_list(
                "after", "through", "observed_at"
            )
        )
        self.assertEqual(before[0]["source_revision"], 1)
        self.adopt()
        self.assertEqual(
            list(
                ExternalPromotionReceipt.objects.order_by("pk").values(
                    "pk",
                    "source_contact_id",
                    "source_revision",
                    "source_hash",
                    "connection",
                )
            ),
            before,
        )
        self.assertEqual(
            list(
                PromotionImportObservation.objects.order_by("after").values_list(
                    "after", "through", "observed_at"
                )
            ),
            spans,
        )
        with override_settings(PROMOTION_SYNC=PromotionSyncConfig(bindings=())):
            body = self.imported(
                [self.entry(8023, self.recipient)], after=8022, through=8023
            )
        self.assertEqual(self.statuses(body), ["applied"])
        self.assertEqual(
            self.receipt(8023).connection_id, self.issued.token.connection_id
        )

    def test_disabled_adopted_stream_never_falls_back(self) -> None:
        connection = self.adopt()
        OrgApiConnection.objects.filter(pk=connection.pk).update(enabled=False)
        unbound = self.completed_event
        OrgApiPromotionEventBinding.objects.filter(event=unbound).delete()
        enabled = replace(settings.PROMOTION_ADAPTOR, enabled=True, api_key="k")
        with override_settings(PROMOTION_ADAPTOR=enabled):
            resolved = resolve_promotion_config(self.org.pk)
            self.assertEqual(
                (resolved.source, resolved.transport), ("connection", "held")
            )
            self.assertNotIn(self.org.pk, {b.org_id for b in env_dispatch_bindings()})
            with self.assertRaises(IntegrationError) as missing:
                get_event_binding(self.org.pk, unbound.pk)
            self.assertEqual(missing.exception.code, "binding_missing")
            self.assertFalse(contact_sync_status(self.org, unbound)["configured"])
            self.assertTrue(contact_sync_status(self.org, self.event)["configured"])
        OrgApiPromotionBinding.objects.filter(connection=connection).delete()
        with self.assertRaises(IntegrationError) as gone:
            get_org_binding(self.org.pk)
        self.assertEqual(gone.exception.code, "binding_missing")


class AdoptedDispatchTests(_DispatchFixture):
    def test_adopted_org_rows_are_not_sent_over_env_transport(self) -> None:
        self.org.discord_server_id = "555000000000000001"
        self.org.save()
        connection = OrgApiConnection.objects.create(
            organization=self.org, name="Stream"
        )
        binding = OrgApiPromotionBinding.objects.create(
            organization=self.org, connection=connection, guild_id="555000000000000001"
        )
        OrgApiPromotionEventBinding.objects.create(
            binding=binding, event=self.event, occasion_id=88
        )
        OrgApiPromotionAdoption.objects.create(
            organization=self.org, connection=connection
        )
        send = self._send(self.promoter)
        client = FakeClient(applied)
        report = self.dispatch(client)
        self.assertEqual(client.calls, [])
        self.assertEqual(report.skipped_unbound, 1)
        self.assertEqual(self.row(send).state, OutboxState.PENDING)


@override_settings(ORG_API_CREDENTIAL_KEYS=json.dumps([OLD_KEY]))
class AdoptionCommandTests(_AdoptionBase):
    def test_command_adopts_and_reports_fixed_codes(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".key") as fh:
            fh.write(PER_ORG_KEY + "\n")
            fh.flush()
            args = [
                "adopt_org_promotion_sync",
                "--org",
                str(self.org.pk),
                "--operator",
                self.operator.username,
                "--base-url",
                BASE_URL,
                "--credential-file",
                fh.name,
            ]
            out = io.StringIO()
            call_command(*args, "--dry-run", stdout=out)
            self.assertIn(
                f"would adopt promotion stream on connection "
                f"{self.issued.token.connection_id}",
                out.getvalue(),
            )
            self.assertNotIn(PER_ORG_KEY, out.getvalue())
            self.assertFalse(OrgApiPromotionAdoption.objects.exists())
            call_command(*args, stdout=out)
            self.assertTrue(OrgApiPromotionAdoption.objects.exists())
            with self.assertRaisesMessage(CommandError, "promotion_stream_exists"):
                call_command(*args, stdout=out)


@override_settings(ORG_API_CREDENTIAL_KEYS=json.dumps([OLD_KEY]))
class PromotionBindingApiTests(_AdoptionBase):
    def setUp(self) -> None:
        super().setUp()
        self.session = APIClient()
        self.session.force_authenticate(self.admin)
        self.connection = OrgApiConnection.objects.create(
            organization=self.other_org, name="Stream"
        )

    def url(self, connection: OrgApiConnection) -> str:
        return (
            f"/api/organizations/{connection.organization_id}/api-connections/"
            f"{connection.pk}/promotion-binding/"
        )

    def put(
        self, connection: OrgApiConnection, events: list[tuple[int, int]]
    ) -> Response:
        return self.session.put(
            self.url(connection),
            {
                "events": [
                    {"event_id": str(event), "occasion_id": str(occasion)}
                    for event, occasion in events
                ]
            },
            format="json",
        )

    def test_deployment_managed_org_is_read_only(self) -> None:
        connection = OrgApiConnection.objects.create(organization=self.org, name="X")
        resp = self.put(connection, [(self.event.pk, 77)])
        self.assertEqual(resp.status_code, 409, resp.data)
        self.assertEqual(resp.data["code"], "managed_by_deployment")
        status = self.session.get(
            f"/api/organizations/{self.org.pk}/api-connections/promotion/"
        )
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.data["source"], "deployment")
        self.assertFalse(status.data["adopted"])

    def test_org_binding_enforces_single_stream_guild_and_events(self) -> None:
        self.other_org.admins.add(self.admin)
        other_event = self.event.__class__.objects.create(
            organization=self.other_org,
            name="Other",
            scheduled_at=self.event.scheduled_at,
            created_by=self.admin,
        )
        resp = self.put(self.connection, [(other_event.pk, 5)])
        self.assertEqual(resp.data["code"], "guild_missing")
        self.other_org.discord_server_id = "880000000000000001"
        self.other_org.save()
        resp = self.put(self.connection, [(self.event.pk, 5)])
        self.assertEqual((resp.status_code, resp.data["code"]), (400, "foreign_event"))
        bad = self.session.put(
            self.url(self.connection),
            {"events": [{"event_id": 5, "occasion_id": "5"}]},
            format="json",
        )
        self.assertEqual(bad.data["code"], "invalid_binding")
        resp = self.put(self.connection, [(other_event.pk, 5)])
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["source"], "connection")
        self.assertEqual(resp.data["guild_id"], "880000000000000001")
        self.assertEqual(resp.data["transport"], "held")
        second = OrgApiConnection.objects.create(organization=self.other_org, name="Y")
        resp = self.put(second, [(other_event.pk, 6)])
        self.assertEqual(resp.data["code"], "promotion_stream_exists")
        detail = self.session.get(
            f"/api/organizations/{self.other_org.pk}/api-connections/"
        )
        flags = {row["id"]: row["promotion_stream"] for row in detail.data}
        self.assertEqual(flags, {self.connection.pk: True, second.pk: False})

    def test_binding_and_destination_edits_after_receipts_blocked(self) -> None:
        self.other_org.admins.add(self.admin)
        self.other_org.discord_server_id = "880000000000000001"
        self.other_org.save()
        event = self.event.__class__.objects.create(
            organization=self.other_org,
            name="Other",
            scheduled_at=self.event.scheduled_at,
            created_by=self.admin,
        )
        self.assertEqual(self.put(self.connection, [(event.pk, 5)]).status_code, 200)
        patch_url = (
            f"/api/organizations/{self.other_org.pk}/api-connections/"
            f"{self.connection.pk}/"
        )
        self.connection.refresh_from_db()
        ok = self.session.patch(
            patch_url,
            {
                "config_version": self.connection.config_version,
                "outbound_base_url": "https://a.example",
            },
            format="json",
        )
        self.assertEqual(ok.status_code, 200, ok.data)
        ExternalPromotionReceipt.objects.create(
            organization=self.other_org,
            source="contact_log",
            source_contact_id=1,
            recorded_at=self.event.scheduled_at,
            contact_date_ny=self.event.scheduled_at.date(),
            contact_method="DISCORD_DM",
            contact_reason="EVENT_INVITE",
            occasion_id=5,
            source_hash="x" * 64,
            discord_id="1",
            event=event,
        )
        resp = self.put(self.connection, [(event.pk, 6)])
        self.assertEqual(resp.data["code"], "binding_locked")
        resp = self.put(self.connection, [])
        self.assertEqual(resp.data["code"], "binding_locked")
        self.assertEqual(self.put(self.connection, [(event.pk, 5)]).status_code, 200)
        blocked = self.session.patch(
            patch_url,
            {
                "config_version": ok.data["config_version"],
                "outbound_base_url": "https://b.example",
            },
            format="json",
        )
        self.assertEqual(blocked.status_code, 409, blocked.data)
        self.assertEqual(blocked.data["code"], "binding_locked")

    def test_first_destination_after_receipts_allowed(self) -> None:
        self.other_org.admins.add(self.admin)
        self.other_org.discord_server_id = "880000000000000001"
        self.other_org.save()
        event = self.event.__class__.objects.create(
            organization=self.other_org,
            name="Other",
            scheduled_at=self.event.scheduled_at,
            created_by=self.admin,
        )
        self.assertEqual(self.put(self.connection, [(event.pk, 5)]).status_code, 200)
        ExternalPromotionReceipt.objects.create(
            organization=self.other_org,
            source="contact_log",
            source_contact_id=1,
            recorded_at=self.event.scheduled_at,
            contact_date_ny=self.event.scheduled_at.date(),
            contact_method="DISCORD_DM",
            contact_reason="EVENT_INVITE",
            occasion_id=5,
            source_hash="x" * 64,
            discord_id="1",
            event=event,
        )
        patch_url = (
            f"/api/organizations/{self.other_org.pk}/api-connections/"
            f"{self.connection.pk}/"
        )
        self.connection.refresh_from_db()
        first = self.session.patch(
            patch_url,
            {
                "config_version": self.connection.config_version,
                "outbound_base_url": "https://a.example",
            },
            format="json",
        )
        self.assertEqual(first.status_code, 200, first.data)
        for url in ("https://b.example", ""):
            moved = self.session.patch(
                patch_url,
                {
                    "config_version": first.data["config_version"],
                    "outbound_base_url": url,
                },
                format="json",
            )
            self.assertEqual(moved.status_code, 409, moved.data)
            self.assertEqual(moved.data["code"], "binding_locked")

    def test_promotion_grants_only_on_stream_connection(self) -> None:
        self.other_org.admins.add(self.admin)
        self.other_org.discord_server_id = "880000000000000001"
        self.other_org.save()
        event = self.event.__class__.objects.create(
            organization=self.other_org,
            name="Other",
            scheduled_at=self.event.scheduled_at,
            created_by=self.admin,
        )
        self.assertEqual(self.put(self.connection, [(event.pk, 5)]).status_code, 200)
        base = f"/api/organizations/{self.other_org.pk}/api-connections/"
        rival = OrgApiConnection.objects.create(organization=self.other_org, name="B")
        for operations in (["promotion:write"], ["promotion:read"]):
            resp = self.session.patch(
                f"{base}{rival.pk}/",
                {"config_version": rival.config_version, "operations": operations},
                format="json",
            )
            self.assertEqual(resp.status_code, 409, resp.data)
            self.assertEqual(resp.data["code"], "promotion_stream_exists")
        created = self.session.post(
            base, {"name": "C", "operations": ["promotion:import"]}, format="json"
        )
        self.assertEqual(created.status_code, 409, created.data)
        self.assertEqual(created.data["code"], "promotion_stream_exists")
        self.connection.refresh_from_db()
        own = self.session.patch(
            f"{base}{self.connection.pk}/",
            {
                "config_version": self.connection.config_version,
                "operations": ["promotion:import", "promotion:read"],
            },
            format="json",
        )
        self.assertEqual(own.status_code, 200, own.data)

    def test_binding_refuses_fresh_connection_beside_legacy_stream(self) -> None:
        self.other_org.admins.add(self.admin)
        self.other_org.discord_server_id = "880000000000000001"
        self.other_org.save()
        event = self.event.__class__.objects.create(
            organization=self.other_org,
            name="Other",
            scheduled_at=self.event.scheduled_at,
            created_by=self.admin,
        )
        legacy = OrgApiConnection.objects.create(
            organization=self.other_org,
            name="Legacy promotion",
            operations=["promotion:import"],
            legacy_multi_credential=True,
        )
        resp = self.put(self.connection, [(event.pk, 5)])
        self.assertEqual(resp.status_code, 409, resp.data)
        self.assertEqual(resp.data["code"], "promotion_stream_exists")
        self.assertFalse(OrgApiPromotionAdoption.objects.exists())
        resp = self.put(legacy, [(event.pk, 5)])
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["connection_id"], legacy.pk)

    def _adopted_other_stream(self) -> Event:
        self.other_org.admins.add(self.admin)
        self.other_org.discord_server_id = "880000000000000001"
        self.other_org.save()
        event = self.event.__class__.objects.create(
            organization=self.other_org,
            name="Other",
            scheduled_at=self.event.scheduled_at,
            created_by=self.admin,
        )
        self.assertEqual(self.put(self.connection, [(event.pk, 5)]).status_code, 200)
        return event

    def test_archived_stream_without_receipts_can_be_replaced(self) -> None:
        event = self._adopted_other_stream()
        base = f"/api/organizations/{self.other_org.pk}/api-connections/"
        archived = self.session.delete(f"{base}{self.connection.pk}/")
        self.assertEqual(archived.status_code, 200, archived.data)
        resp = self.put(self.connection, [(event.pk, 5)])
        self.assertEqual(resp.data["code"], "connection_archived")
        fresh = OrgApiConnection.objects.create(organization=self.other_org, name="N")
        resp = self.put(fresh, [(event.pk, 7)])
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["connection_id"], fresh.pk)
        adoption = OrgApiPromotionAdoption.objects.get(organization=self.other_org)
        self.assertEqual(adoption.connection_id, fresh.pk)
        self.assertFalse(
            OrgApiPromotionBinding.objects.filter(connection=self.connection).exists()
        )

    def test_stream_with_receipts_cannot_be_archived(self) -> None:
        event = self._adopted_other_stream()
        ExternalPromotionReceipt.objects.create(
            organization=self.other_org,
            source="contact_log",
            source_contact_id=1,
            recorded_at=self.event.scheduled_at,
            contact_date_ny=self.event.scheduled_at.date(),
            contact_method="DISCORD_DM",
            contact_reason="EVENT_INVITE",
            occasion_id=5,
            source_hash="x" * 64,
            discord_id="1",
            event=event,
        )
        base = f"/api/organizations/{self.other_org.pk}/api-connections/"
        resp = self.session.delete(f"{base}{self.connection.pk}/")
        self.assertEqual(resp.status_code, 409, resp.data)
        self.assertEqual(resp.data["code"], "promotion_stream_in_use")
        self.connection.refresh_from_db()
        self.assertIsNone(self.connection.archived_at)
        other = OrgApiConnection.objects.create(organization=self.other_org, name="O")
        self.assertEqual(self.session.delete(f"{base}{other.pk}/").status_code, 200)


class ObservationProvenanceTests(_ImportBase):
    def batch_at(self, observed: datetime, after: int, through: int) -> ImportBatch:
        return ImportBatch(
            guild_id=GUILD,
            scan_started_at=observed,
            range_after=after,
            range_through=through,
            skipped_ids=frozenset(),
            entries=[],
        )

    def test_same_observation_time_keeps_each_connection(self) -> None:
        first = self.issued.token.connection
        second = OrgApiConnection.objects.create(organization=self.org, name="Two")
        observed = timezone.now()
        record_ranges(
            self.org.pk, self.batch_at(observed, 0, 10), connection_id=first.pk
        )
        record_ranges(
            self.org.pk, self.batch_at(observed, 20, 30), connection_id=second.pk
        )
        record_ranges(
            self.org.pk,
            self.batch_at(observed - timedelta(minutes=1), 40, 50),
            connection_id=None,
        )
        self.assertEqual(
            list(
                PromotionImportObservation.objects.order_by("after").values_list(
                    "after", "through", "connection_id"
                )
            ),
            [(0, 10, first.pk), (20, 30, second.pk), (40, 50, None)],
        )
