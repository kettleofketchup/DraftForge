"""Importing the bound guild's external contact log.

POST ``/api/organizations/{org}/integration/v1/contact-receipts/`` takes one
id range of the external contact log: every row the adaptor read with
``after < id <= through`` is either an entry or a skipped id. Each entry is
stored once, keyed by ``(org, source, source_contact_id)``, whoever the
player is: an unknown player is stored with no account. An occasion bound to
one of the org's events maps the contact to that event; any other occasion,
and every date-linked contact, is stored with no event and earns nothing.

A replay with the same source facts, target, promoter and bound event is
``unchanged`` and keeps the original import time. Any difference is
``updated`` (a supersede, audited in the org log). A stored contact inside a
posted range that is neither posted nor skipped was deleted at the source and
is retracted, unless a newer scan than this one imported it; posting it
again reinstates it. The import never creates an account, a membership or a
``PromoSend``.

Imported invitations tick the promoter's candidate rows
(``contact_recorded`` / ``external_contact``), are hidden by "Hide messaged"
and block a new ordinary send with 409 ``contact_already_recorded``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

from django.core.cache import cache
from django.db import IntegrityError, models
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser
from config.promotion_sync import PromotionSyncConfig
from events.constants import EventState
from events.models import Event
from org.api_tokens.tokens import issue_token
from org.feature_keys import FeatureKey
from org.features import set_org_feature
from org.integration.contacts import external_contact_for, reconcile_association
from org.integration.lifecycle import reconcile_promotion_identity
from org.integration.receipts import format_timestamp
from org.membership import resolve_or_create_org_user
from org.models import ContributionEntry, Organization, OrgLog, OrgUser, PromoSend
from org.models_promotion_sync import (
    AssociationReason,
    AssociationState,
    ContactReason,
    ExternalPromotionReceipt,
    PointStatus,
)
from org.promotion.recipients import user_for_guild_member
from org.promotion.services import record_promo_send, undo_promo_send
from org.tests.test_api_tokens import LOCMEM_CACHE
from org.tests.test_promotion_api import PromotionApiBase, base
from tournament.models import Tournament
from user.discord_accounts import merge_discord_accounts

GUILD = "770000000000000001"
FETCH = "org.promotion.recipients.get_discord_members_data"
GUILD_ONLY_ID = "990000000000000001"
SECOND_GUILD_ID = "990000000000000003"
UNKNOWN_ID = "990000000000000099"
OCCASION = 88
COMPLETED_OCCASION = 89
UNBOUND_OCCASION = 4242
RECORDED = "2026-11-01T10:00:00Z"
CONTACT_DATE = "2026-11-01"


def guild_member(discord_id: str, *, days_ago: float, bot: bool = False) -> dict:
    joined = timezone.now() - timedelta(days=days_ago)
    return {
        "user": {
            "id": discord_id,
            "username": f"g{discord_id[-4:]}",
            "global_name": None,
            "avatar": None,
            **({"bot": True} if bot else {}),
        },
        "nick": None,
        "joined_at": joined.isoformat(),
    }


def bindings(org: Organization, events: dict[Event, int]) -> PromotionSyncConfig:
    raw = json.dumps(
        [
            {
                "org_id": str(org.pk),
                "guild_id": GUILD,
                "events": [
                    {"event_id": str(e.pk), "occasion_id": str(occasion)}
                    for e, occasion in events.items()
                ],
            }
        ]
    )
    return PromotionSyncConfig.from_env(environ={"PROMOTION_SYNC_BINDINGS": raw})


def age_import(receipt_id: int, *, minutes: int = 30) -> None:
    """Move a receipt's import time back, as if an older scan stored it.

    ``first_imported_at`` is frozen for application code; the plain
    queryset update skips that guard on purpose.
    """
    models.QuerySet.update(
        ExternalPromotionReceipt.objects.filter(pk=receipt_id),
        first_imported_at=timezone.now() - timedelta(minutes=minutes),
    )


@override_settings(CACHES=LOCMEM_CACHE, DISCORD_BOT_TOKEN="test-bot-token")
class _ImportBase(PromotionApiBase):
    def setUp(self) -> None:
        super().setUp()
        cache.clear()
        self.org.discord_server_id = GUILD
        self.org.save()
        self.admin = self.users["admin"]
        assert self.admin is not None
        self.issued = issue_token(
            self.org, self.admin, "contact-log-import", operations=["promotion:import"]
        )
        self.members: list[dict[str, Any]] = [
            guild_member(GUILD_ONLY_ID, days_ago=5),
            guild_member(SECOND_GUILD_ID, days_ago=5),
        ]
        self.bind({self.event: OCCASION, self.completed_event: COMPLETED_OCCASION})
        fetch = patch(FETCH, side_effect=lambda **_: list(self.members))
        self.fetch = fetch.start()
        self.addCleanup(fetch.stop)

    def bind(self, events: dict[Event, int]) -> None:
        override = override_settings(PROMOTION_SYNC=bindings(self.org, events))
        override.enable()
        self.addCleanup(override.disable)

    def assertError(self, resp, status: int, code: str) -> None:
        self.assertEqual(resp.status_code, status, resp.content)
        self.assertEqual(resp.json()["error"]["code"], code)

    def bearer(self, raw: str | None = None) -> APIClient:
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {raw or self.issued.raw}")
        return client

    def import_url(self, org: Organization | None = None) -> str:
        return (
            f"/api/organizations/{(org or self.org).pk}/integration/v1/"
            "contact-receipts/"
        )

    @staticmethod
    def discord(who: CustomUser | str) -> str:
        if isinstance(who, str):
            return who
        who.refresh_from_db()
        assert who.discordId
        return who.discordId

    def entry(
        self,
        source_id: int,
        who: CustomUser | str,
        *,
        promoter: CustomUser | str | None = None,
        event: Event | None = None,
        **overrides: Any,
    ) -> dict[str, Any]:
        occasion = COMPLETED_OCCASION if event == self.completed_event else OCCASION
        data = {
            "source_contact_id": str(source_id),
            "target_discord_id": self.discord(who),
            "promoter_discord_id": None if promoter is None else self.discord(promoter),
            "recorded_at": RECORDED,
            "contact_date_ny": CONTACT_DATE,
            "contact_method": "DISCORD_DM",
            "contact_reason": "EVENT_INVITE",
            "occasion_id": str(occasion),
            "event_date": None,
            "forced": False,
        }
        data.update(overrides)
        return data

    def batch(
        self,
        entries: list[dict[str, Any]],
        *,
        after: int | None = None,
        through: int | None = None,
        skipped: list[int] | None = None,
        scan_started_at: datetime | None = None,
        guild: str = GUILD,
    ) -> dict[str, Any]:
        ids = [int(e["source_contact_id"]) for e in entries] + list(skipped or [])
        if through is None and ids:
            through = max(ids)
        if after is None and ids:
            after = min(ids) - 1
        return {
            "source": "contact_log",
            "guild_id": guild,
            "scan_started_at": format_timestamp(scan_started_at or timezone.now()),
            "range": (
                None
                if through is None
                else {"after": str(after or 0), "through": str(through)}
            ),
            "skipped_ids": [str(i) for i in skipped or []],
            "entries": entries,
        }

    def post(
        self,
        entries: list[dict[str, Any]],
        *,
        body: dict[str, Any] | None = None,
        raw: str | None = None,
        org: Organization | None = None,
        **batch: Any,
    ):
        payload = body if body is not None else self.batch(entries, **batch)
        return self.bearer(raw).post(self.import_url(org), payload, format="json")

    def imported(self, entries: list[dict[str, Any]], **kwargs: Any) -> dict:
        resp = self.post(entries, **kwargs)
        self.assertEqual(resp.status_code, 200, resp.content)
        return resp.json()

    def statuses(self, body: dict) -> list[str]:
        self.assertEqual(
            [r["index"] for r in body["results"]], list(range(len(body["results"])))
        )
        return [r["status"] for r in body["results"]]

    def receipt(self, source_id: int) -> ExternalPromotionReceipt:
        return ExternalPromotionReceipt.objects.get(
            organization=self.org, source_contact_id=source_id
        )

    def ticked(self, discord_id: str, user: CustomUser | None) -> bool:
        return (
            external_contact_for(
                self.event.pk, discord_id, user_id=user.pk if user else None
            )
            is not None
        )

    def non_member_player(self, name: str) -> CustomUser:
        """An account in the guild with no membership in the org."""
        user = self._user(name)
        self.members = [*self.members, guild_member(user.discordId, days_ago=3)]
        self.assertFalse(OrgUser.objects.filter(user=user).exists())
        return user


COUNT_KEYS = (
    "applied",
    "unchanged",
    "updated",
    "reinstated",
    "quarantined",
    "association_updated",
    "retracted",
    "credited",
    "uncredited",
    "duplicate",
    "echo",
    "voided_local",
    "restored_local",
)


class ImportTests(_ImportBase):
    def test_new_contacts_apply_with_exact_response(self) -> None:
        body = self.imported(
            [self.entry(8021, self.recipient), self.entry(8022, GUILD_ONLY_ID)]
        )
        self.assertEqual(
            body,
            {
                "results": [
                    {
                        "index": 0,
                        "status": "applied",
                        "point": "uncredited",
                        "voided_local": False,
                    },
                    {
                        "index": 1,
                        "status": "applied",
                        "point": "uncredited",
                        "voided_local": False,
                    },
                ],
                **dict.fromkeys(COUNT_KEYS, 0),
                "applied": 2,
                "uncredited": 2,
                "max_source_contact_id": "8022",
            },
        )
        stored = self.receipt(8021)
        self.assertEqual(stored.user_id, self.recipient.pk)
        self.assertEqual(stored.association_state, AssociationState.LINKED)
        self.assertEqual(stored.recorded_at, datetime(2026, 11, 1, 10, tzinfo=UTC))
        self.assertEqual(stored.event_id, self.event.pk)
        self.assertEqual(stored.occasion_id, OCCASION)
        self.assertEqual(stored.contact_reason, ContactReason.EVENT_INVITE)
        guild_only = self.receipt(8022)
        self.assertIsNone(guild_only.user_id)
        self.assertEqual(guild_only.association_state, AssociationState.UNRESOLVED)

    def test_guild_mismatch_403(self) -> None:
        resp = self.post([self.entry(8021, self.recipient)], guild="770000000000000099")
        self.assertError(resp, 403, "binding_mismatch")
        self.assertFalse(ExternalPromotionReceipt.objects.exists())

    def test_binding_missing_403(self) -> None:
        with override_settings(PROMOTION_SYNC=PromotionSyncConfig(bindings=())):
            resp = self.post([self.entry(8021, self.recipient)])
        self.assertError(resp, 403, "binding_missing")
        self.assertFalse(ExternalPromotionReceipt.objects.exists())

    def test_wrong_org_and_grant_and_feature(self) -> None:
        entries = [self.entry(8021, self.recipient)]
        self.assertEqual(self.post(entries, org=self.other_org).status_code, 404)
        mmr = issue_token(self.org, self.admin, "mmr", operations=["mmr:read"])
        self.assertError(self.post(entries, raw=mmr.raw), 403, "operation_not_granted")
        set_org_feature(self.org, FeatureKey.PROMOTION, enabled=False, actor=None)
        self.assertError(self.post(entries), 403, "feature_locked")
        self.assertFalse(ExternalPromotionReceipt.objects.exists())

    def test_invalid_row_rejects_whole_batch(self) -> None:
        resp = self.post(
            [
                self.entry(8021, self.recipient),
                self.entry(8022, GUILD_ONLY_ID, recorded_at="2026-11-01 10:00"),
            ]
        )
        self.assertError(resp, 400, "invalid_request")
        self.assertIn("entries[1].recorded_at", resp.json()["error"]["message"])
        self.assertFalse(ExternalPromotionReceipt.objects.exists())

    def test_old_wire_rejected(self) -> None:
        body = {
            "source": "contact_log",
            "mapping_version": "a" * 64,
            "entries": [],
        }
        self.assertError(self.post([], body=body), 400, "invalid_request")

    def test_unknown_player_stored_without_user(self) -> None:
        users = CustomUser.objects.count()
        body = self.imported([self.entry(8021, UNKNOWN_ID)])
        self.assertEqual(self.statuses(body), ["applied"])
        stored = self.receipt(8021)
        self.assertIsNone(stored.user_id)
        self.assertIsNone(stored.org_user_id)
        self.assertEqual(stored.discord_id, UNKNOWN_ID)
        self.assertEqual(stored.association_state, AssociationState.UNRESOLVED)
        self.assertEqual(CustomUser.objects.count(), users)

    def test_unbound_occasion_and_date_rows_not_applicable(self) -> None:
        body = self.imported(
            [
                self.entry(8021, self.recipient, occasion_id=str(UNBOUND_OCCASION)),
                self.entry(
                    8022,
                    self.recipient,
                    occasion_id=None,
                    event_date="2026-11-05T00:00:00Z",
                ),
                self.entry(8023, self.recipient, contact_reason="FOLLOW_UP"),
            ]
        )
        self.assertEqual([r["point"] for r in body["results"]], ["not_applicable"] * 3)
        for source_id in (8021, 8022):
            stored = self.receipt(source_id)
            self.assertIsNone(stored.event_id)
            self.assertFalse(stored.holds_point)
        self.assertEqual(self.receipt(8023).event_id, self.event.pk)
        self.assertFalse(self.receipt(8023).holds_point)
        self.assertFalse(self.ticked(self.recipient.discordId, self.recipient))

    def test_event_outside_org_is_not_mapped(self) -> None:
        self.bind({self.other_event: OCCASION})
        self.imported([self.entry(8021, self.recipient)])
        self.assertIsNone(self.receipt(8021).event_id)

    def test_replay_unchanged_keeps_import_time(self) -> None:
        first = [self.entry(8021, self.recipient), self.entry(8022, GUILD_ONLY_ID)]
        self.imported(first)
        before = {
            r.source_contact_id: (r.first_imported_at, r.source_hash, r.source_revision)
            for r in ExternalPromotionReceipt.objects.all()
        }
        body = self.imported(list(reversed(first)))
        self.assertEqual(self.statuses(body), ["unchanged", "unchanged"])
        self.assertEqual((body["applied"], body["unchanged"]), (0, 2))
        after = {
            r.source_contact_id: (r.first_imported_at, r.source_hash, r.source_revision)
            for r in ExternalPromotionReceipt.objects.all()
        }
        self.assertEqual(before, after)
        self.assertFalse(OrgLog.objects.filter(action="update_external_contact"))

    def _assert_updated(self, source_id: int, changed: set[str]) -> None:
        stored = self.receipt(source_id)
        self.assertEqual(stored.source_revision, 1)
        self.assertIsNotNone(stored.source_updated_at)
        log = OrgLog.objects.get(action="update_external_contact")
        self.assertIsNone(log.actor_id)
        self.assertEqual(
            set(log.details),
            {
                "source_contact_id",
                "revision",
                "old_hash",
                "new_hash",
                "changed",
                "old_event_id",
                "new_event_id",
            },
        )
        self.assertEqual(set(log.details["changed"]), changed)
        self.assertEqual(log.details["source_contact_id"], source_id)
        text = json.dumps(log.details)
        for discord_id in (GUILD_ONLY_ID, SECOND_GUILD_ID, self.recipient.discordId):
            self.assertNotIn(discord_id, text)

    def test_updated_on_changed_hash(self) -> None:
        self.imported([self.entry(8021, self.recipient)])
        old_hash = self.receipt(8021).source_hash
        body = self.imported(
            [self.entry(8021, self.recipient, recorded_at="2026-11-02T10:00:00Z")]
        )
        self.assertEqual(self.statuses(body), ["updated"])
        self.assertEqual(body["updated"], 1)
        stored = self.receipt(8021)
        self.assertNotEqual(stored.source_hash, old_hash)
        self.assertEqual(stored.recorded_at, datetime(2026, 11, 2, 10, tzinfo=UTC))
        self._assert_updated(8021, {"recorded_at", "source_hash"})

    def test_updated_on_changed_target(self) -> None:
        self.imported([self.entry(8021, GUILD_ONLY_ID)])
        body = self.imported([self.entry(8021, SECOND_GUILD_ID)])
        self.assertEqual(self.statuses(body), ["updated"])
        stored = self.receipt(8021)
        self.assertEqual(stored.discord_id, SECOND_GUILD_ID)
        self.assertTrue(stored.holds_point)
        self._assert_updated(8021, {"discord_id"})

    def test_updated_on_changed_promoter(self) -> None:
        self.imported([self.entry(8021, GUILD_ONLY_ID)])
        body = self.imported(
            [self.entry(8021, GUILD_ONLY_ID, promoter=self.users["member"])]
        )
        self.assertEqual(self.statuses(body), ["updated"])
        self.assertEqual(
            self.receipt(8021).promoter_discord_id, self.users["member"].discordId
        )
        self._assert_updated(8021, {"promoter_discord_id"})

    def test_updated_on_changed_binding(self) -> None:
        self.imported([self.entry(8021, GUILD_ONLY_ID)])
        self.bind({self.completed_event: OCCASION})
        body = self.imported([self.entry(8021, GUILD_ONLY_ID)])
        self.assertEqual(self.statuses(body), ["updated"])
        stored = self.receipt(8021)
        self.assertEqual(stored.event_id, self.completed_event.pk)
        self._assert_updated(8021, {"event"})
        log = OrgLog.objects.get(action="update_external_contact")
        self.assertEqual(log.details["old_event_id"], self.event.pk)
        self.assertEqual(log.details["new_event_id"], self.completed_event.pk)

    def _two_stored(self) -> None:
        self.imported([self.entry(10, GUILD_ONLY_ID), self.entry(30, SECOND_GUILD_ID)])
        for source_id in (10, 30):
            age_import(self.receipt(source_id).pk)

    def test_retract_inside_range_only(self) -> None:
        self._two_stored()
        body = self.imported([], after=0, through=20)
        self.assertEqual(body["retracted"], 1)
        retracted = self.receipt(10)
        self.assertIsNotNone(retracted.retracted_at)
        self.assertEqual(retracted.point_status, PointStatus.RETRACTED)
        self.assertFalse(retracted.holds_point)
        self.assertIsNone(self.receipt(30).retracted_at)
        self.assertFalse(
            external_contact_for(self.event.pk, GUILD_ONLY_ID, user_id=None)
        )

    def test_skipped_ids_never_retracted(self) -> None:
        self._two_stored()
        body = self.imported([], after=0, through=20, skipped=[10])
        self.assertEqual(body["retracted"], 0)
        self.assertIsNone(self.receipt(10).retracted_at)

    def test_first_imported_guard_blocks_retraction(self) -> None:
        self.imported([self.entry(10, GUILD_ONLY_ID)])
        body = self.imported(
            [], after=0, through=20, scan_started_at=timezone.now() - timedelta(hours=1)
        )
        self.assertEqual(body["retracted"], 0)
        self.assertIsNone(self.receipt(10).retracted_at)

    def test_reinstated_after_retraction(self) -> None:
        self._two_stored()
        self.imported([], after=0, through=20)
        body = self.imported([self.entry(10, GUILD_ONLY_ID)])
        self.assertEqual(self.statuses(body), ["reinstated"])
        self.assertEqual(body["reinstated"], 1)
        stored = self.receipt(10)
        self.assertIsNone(stored.retracted_at)
        self.assertEqual(stored.point_status, PointStatus.UNCREDITED)
        self.assertTrue(stored.holds_point)

    def test_max_source_contact_id_includes_retracted(self) -> None:
        probe = self.imported([])
        self.assertIsNone(probe["max_source_contact_id"])
        self._two_stored()
        body = self.imported([], after=20, through=40)
        self.assertEqual(body["retracted"], 1)
        self.assertEqual(body["max_source_contact_id"], "30")
        self.assertEqual(self.imported([])["max_source_contact_id"], "30")

    def test_import_creates_no_users_members_or_sends(self) -> None:
        player = self.non_member_player("np")
        users, org_users = CustomUser.objects.count(), OrgUser.objects.count()
        self.imported(
            [
                self.entry(8021, self.recipient),
                self.entry(8022, UNKNOWN_ID, promoter=self.recipient),
                self.entry(8023, player, promoter=UNKNOWN_ID),
            ]
        )
        self.assertEqual(CustomUser.objects.count(), users)
        self.assertEqual(OrgUser.objects.count(), org_users)
        self.assertFalse(PromoSend.objects.exists())

    def test_concurrent_source_id_insert_is_a_retryable_conflict(self) -> None:
        with patch(
            "org.integration.contacts._apply_batch",
            side_effect=IntegrityError("unique constraint"),
        ):
            resp = self.post([self.entry(8021, self.recipient)])
        self.assertError(resp, 409, "import_conflict_retry")
        self.assertFalse(ExternalPromotionReceipt.objects.exists())

    def test_import_never_reads_the_guild(self) -> None:
        self.imported([self.entry(8021, GUILD_ONLY_ID)])
        self.fetch.assert_not_called()

    def test_recipients_route_removed_404(self) -> None:
        resp = self.bearer().get(
            f"/api/organizations/{self.org.pk}/integration/v1/events/"
            f"{self.event.pk}/recipients/"
        )
        self.assertEqual(resp.status_code, 404)

    def test_promotion_read_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown operation"):
            issue_token(self.org, self.admin, "old", operations=["promotion:read"])
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            f"/api/organizations/{self.org.pk}/api-tokens/",
            {"name": "old", "operations": ["promotion:read"]},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)


class AssociationRescanTests(_ImportBase):
    """Association changes on replay are reconciled, never superseded."""

    def _assert_enriched(self, source_id: int, before: ExternalPromotionReceipt):
        after = self.receipt(source_id)
        self.assertEqual(after.source_hash, before.source_hash)
        self.assertEqual(after.first_imported_at, before.first_imported_at)
        self.assertEqual(after.association_state, AssociationState.LINKED)
        return after

    def test_rescan_after_null_user_resolution(self) -> None:
        self.imported([self.entry(8021, GUILD_ONLY_ID)])
        before = self.receipt(8021)
        self.assertTrue(self.ticked(GUILD_ONLY_ID, None))

        resolved = user_for_guild_member(guild_member(GUILD_ONLY_ID, days_ago=5))
        body = self.imported(
            [self.entry(8021, GUILD_ONLY_ID), self.entry(8030, self.recipient)]
        )
        self.assertEqual(self.statuses(body), ["unchanged", "applied"])
        self.assertEqual(body["association_updated"], 1)
        after = self._assert_enriched(8021, before)
        self.assertEqual(after.user_id, resolved.pk)
        self.assertTrue(self.ticked(GUILD_ONLY_ID, resolved))

    def test_rescan_after_org_user_creation(self) -> None:
        player = self.non_member_player("future_member")
        self.imported([self.entry(8021, player)])
        before = self.receipt(8021)
        self.assertIsNone(before.org_user_id)

        org_user = resolve_or_create_org_user(player, self.org)
        body = self.imported([self.entry(8021, player)])
        self.assertEqual(self.statuses(body), ["unchanged"])
        self.assertEqual(body["association_updated"], 1)
        after = self._assert_enriched(8021, before)
        self.assertEqual(after.org_user_id, org_user.pk)

    def test_rescan_after_verified_merge(self) -> None:
        drop = self.non_member_player("merge_drop")
        discord_id = drop.discordId
        self.imported([self.entry(8021, drop)])
        before = self.receipt(8021)

        keep = self._user("merge_keep")
        CustomUser.objects.filter(pk=drop.pk).update(discordId=None)
        CustomUser.objects.filter(pk=keep.pk).update(discordId=discord_id)
        keep.refresh_from_db()
        drop.refresh_from_db()
        reconcile_promotion_identity(keep, drop)
        merge_discord_accounts(keep, drop)

        body = self.imported([self.entry(8021, keep)])
        self.assertEqual(self.statuses(body), ["unchanged"])
        after = self._assert_enriched(8021, before)
        self.assertEqual(after.user_id, keep.pk)
        self.assertTrue(self.ticked(discord_id, keep))

    def test_rescan_conflicting_owner_quarantines_entry_only(self) -> None:
        first_owner = self.non_member_player("first_owner")
        discord_id = first_owner.discordId
        self.imported([self.entry(8021, first_owner)])
        before = self.receipt(8021)

        CustomUser.objects.filter(pk=first_owner.pk).update(
            discordId="880000000000000555"
        )
        CustomUser.objects.create_user(
            username="new_owner", password="x", discordId=discord_id
        )
        body = self.imported(
            [self.entry(8021, discord_id), self.entry(8033, GUILD_ONLY_ID)]
        )
        self.assertEqual(self.statuses(body), ["quarantined", "applied"])
        self.assertEqual(body["quarantined"], 1)
        self.assertEqual(body["association_updated"], 0)
        after = self.receipt(8021)
        self.assertEqual(after.association_state, AssociationState.QUARANTINED)
        self.assertEqual(
            after.association_reason, AssociationReason.DISCORD_OWNER_CHANGED
        )
        self.assertEqual(after.user_id, first_owner.pk)
        self.assertEqual(after.source_hash, before.source_hash)

        again = self.imported([self.entry(8021, discord_id)])
        self.assertEqual(self.statuses(again), ["quarantined"])

    def test_membership_of_another_user_quarantines(self) -> None:
        player = self.non_member_player("ou_player")
        self.imported([self.entry(8021, player)])
        stored = self.receipt(8021)
        other = OrgUser.objects.create(
            user=self._user("ou_other"), organization=self.org
        )
        outcome = reconcile_association(stored, player.pk, other.pk)
        self.assertEqual(outcome.status, "quarantined")
        self.assertFalse(outcome.association_updated)
        stored.refresh_from_db()
        self.assertEqual(stored.association_reason, AssociationReason.ORG_USER_MISMATCH)


@override_settings(DISCORD_BOT_TOKEN="test-bot-token")
class CandidateSuppressionTests(_ImportBase):
    def candidates(self, **params: Any) -> dict:
        resp = self.request("promoter", "get", self.candidates_url(), params)
        self.assertEqual(resp.status_code, 200, resp.content)
        return resp.json()

    def row(self, body: dict, discord_id: str) -> dict | None:
        return next((r for r in body["rows"] if r["discordId"] == discord_id), None)

    def setUp(self) -> None:
        super().setUp()
        self.active_player = self._user("active_player")
        Tournament.objects.create(
            name="Active cup",
            date_played=timezone.now() - timedelta(days=40),
            league=self.league,
        ).users.add(self.active_player)
        self.joiner = self._user("joiner")
        self.members = [*self.members, guild_member(self.joiner.discordId, days_ago=2)]

    def _import_all(self) -> None:
        self.imported(
            [
                self.entry(8021, self.recipient),
                self.entry(8022, self.active_player),
                self.entry(8023, self.joiner),
                self.entry(8024, GUILD_ONLY_ID),
            ]
        )

    def test_hidden_by_default_across_sources(self) -> None:
        sources = {
            "recent": self.recipient.discordId,
            "active": self.active_player.discordId,
            "discord": self.joiner.discordId,
        }
        for source, discord_id in sources.items():
            self.assertIsNotNone(
                self.row(self.candidates(source=source, days=90, n=10), discord_id),
                source,
            )
        self._import_all()
        for source, discord_id in sources.items():
            with self.subTest(source=source):
                body = self.candidates(source=source, days=90, n=10)
                self.assertIsNone(self.row(body, discord_id))
        self.assertIsNone(
            self.row(self.candidates(source="discord", days=90), GUILD_ONLY_ID)
        )

    def test_shown_rows_report_external_contact(self) -> None:
        self._import_all()
        for source, discord_id in (
            ("recent", self.recipient.discordId),
            ("active", self.active_player.discordId),
            ("discord", self.joiner.discordId),
            ("discord", GUILD_ONLY_ID),
        ):
            with self.subTest(source=source, discord_id=discord_id):
                body = self.candidates(
                    source=source, days=90, n=10, hide_messaged="false"
                )
                row = self.row(body, discord_id)
                assert row is not None
                self.assertTrue(row["contact_recorded"])
                self.assertIsNone(row["last_messaged"])
                self.assertEqual(
                    row["external_contact"],
                    {
                        "source": "contact_log",
                        "recorded_at": RECORDED,
                        "delivery_verified": False,
                        "can_undo": False,
                    },
                )

    def test_untouched_rows_have_no_contact(self) -> None:
        body = self.candidates(hide_messaged="false")
        row = self.row(body, self.recipient.discordId)
        assert row is not None
        self.assertFalse(row["contact_recorded"])
        self.assertIsNone(row["external_contact"])

    def test_contact_sync_metadata(self) -> None:
        body = self.candidates()
        self.assertEqual(
            body["contact_sync"],
            {
                "configured": True,
                "last_receipt_imported_at": None,
                "warning": "history_may_be_incomplete",
            },
        )
        self._import_all()
        stamp = self.candidates()["contact_sync"]["last_receipt_imported_at"]
        self.assertIsNotNone(stamp)

    def test_org_without_bindings_unchanged(self) -> None:
        with override_settings(PROMOTION_SYNC=PromotionSyncConfig(bindings=())):
            body = self.candidates(hide_messaged="false")
        self.assertEqual(
            body["contact_sync"],
            {"configured": False, "last_receipt_imported_at": None, "warning": None},
        )
        row = self.row(body, self.recipient.discordId)
        assert row is not None
        self.assertFalse(row["contact_recorded"])

    def test_retracted_and_other_reason_contacts_do_not_tick(self) -> None:
        self.imported([self.entry(8022, self.recipient, contact_reason="GENERAL")])
        self.assertFalse(self.ticked(self.recipient.discordId, self.recipient))
        self.imported([self.entry(8021, self.recipient)])
        age_import(self.receipt(8021).pk)
        self.imported([], after=8020, through=8021)
        self.assertFalse(self.ticked(self.recipient.discordId, self.recipient))

    def test_local_and_external_undo_removes_only_local(self) -> None:
        send = record_promo_send(
            sender=self.users["promoter"],
            event=self.event,
            recipient=self.recipient,
            template=None,
            text="Hi",
        )
        self.imported([self.entry(8021, self.recipient)])
        row = self.row(self.candidates(hide_messaged="false"), self.recipient.discordId)
        assert row is not None
        self.assertEqual(row["last_messaged"]["send_id"], send.pk)
        self.assertIsNotNone(row["external_contact"])

        undo_promo_send(send, actor=self.users["promoter"])
        self.assertFalse(ContributionEntry.objects.nocache().exists())
        row = self.row(self.candidates(hide_messaged="false"), self.recipient.discordId)
        assert row is not None
        self.assertIsNone(row["last_messaged"])
        self.assertTrue(row["contact_recorded"])
        self.assertTrue(self.receipt(8021))

    def test_send_to_externally_contacted_is_409(self) -> None:
        self.imported([self.entry(8021, self.recipient)])
        resp = self.request(
            "promoter",
            "post",
            self.sends_url(),
            {"recipient_id": self.recipient.pk, "text": "Hi"},
        )
        self.assertEqual(resp.status_code, 409, resp.content)
        self.assertEqual(resp.json()["code"], "contact_already_recorded")
        self.assertFalse(PromoSend.objects.exists())
        self.assertFalse(ContributionEntry.objects.nocache().exists())

    def test_local_only_repeat_send_still_succeeds(self) -> None:
        for expected in (True, False):
            resp = self.request(
                "promoter",
                "post",
                self.sends_url(),
                {"recipient_id": self.recipient.pk, "text": "Hi"},
            )
            self.assertEqual(resp.status_code, 201, resp.content)
            self.assertEqual(resp.json()["earns_points"], expected)

    def test_resolving_discord_member_row_carries_contact(self) -> None:
        self.imported([self.entry(8024, GUILD_ONLY_ID)])
        users = CustomUser.objects.count()
        resp = self.request(
            "promoter",
            "post",
            f"{base(self.org.pk)}events/{self.event.pk}/candidates/discord/",
            {"discord_id": GUILD_ONLY_ID},
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(CustomUser.objects.count(), users + 1)
        self.assertTrue(resp.json()["contact_recorded"])
        self.assertIsNotNone(resp.json()["external_contact"])

    def test_import_invalidates_cached_candidates(self) -> None:
        with patch("org.promotion.recipients.guild_members", return_value=[]):
            first = self.candidates()
            self.assertIsNotNone(self.row(first, self.recipient.discordId))
            self.imported([self.entry(8021, self.recipient)])
            self.assertIsNone(self.row(self.candidates(), self.recipient.discordId))


class UnboundEventTests(_ImportBase):
    def test_new_unbound_event_gets_no_contacts(self) -> None:
        unbound = Event.objects.create(
            organization=self.org,
            name="Unbound",
            scheduled_at=timezone.now() + timedelta(days=4),
            created_by=self.admin,
            state=EventState.UPCOMING,
        )
        self.imported([self.entry(8021, self.recipient)])
        self.assertFalse(
            ExternalPromotionReceipt.objects.filter(event=unbound).exists()
        )
