"""Importing SFG contact receipts as event-scoped promotion suppression.

POST ``/api/organizations/{org}/integration/v1/contact-receipts/`` stores
each SFG contact once, keyed by ``(org, source, source_contact_id)``. Its
source facts are immutable: a rescan with the same facts is ``unchanged``
and keeps the original import time, and changed facts are 409
``source_content_conflict`` for the whole batch. The DraftForge association
(user, membership) may be enriched by a verified resolution, or quarantined
for that entry alone when the Discord ID now belongs to someone else.

Imported receipts tick the promoter's existing candidate rows
(``contact_recorded`` / ``external_contact``), are hidden by "Hide messaged"
and block a new ordinary send with 409 ``contact_already_recorded``. They
never create a send, an award, an account or a membership.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

from django.db import IntegrityError
from django.test import override_settings
from django.utils import timezone

from app.models import CustomUser
from discordbot.services.discord_members import DiscordMembersFetchError
from events.constants import EventState
from events.models import Event
from org.api_tokens.tokens import issue_token
from org.feature_keys import FeatureKey
from org.features import set_org_feature
from org.integration import contacts
from org.integration.contacts import external_contact_for
from org.integration.lifecycle import reconcile_promotion_identity
from org.integration.subjects import authorized_event_subjects
from org.membership import resolve_or_create_org_user
from org.models import ContributionEntry, Organization, OrgUser, PromoSend
from org.models_promotion_sync import (
    AssociationReason,
    AssociationState,
    ExternalPromotionReceipt,
)
from org.promotion.recipients import user_for_guild_member
from org.promotion.services import record_promo_send, undo_promo_send
from org.tests.test_integration_recipients import (
    FETCH,
    GUILD_ONLY_ID,
    _RecipientsBase,
    bindings,
    guild_member,
)
from org.tests.test_promotion_api import base
from tournament.models import Tournament
from user.discord_accounts import merge_discord_accounts

RECORDED = "2026-11-01T10:00:00Z"
SECOND_GUILD_ID = "990000000000000003"


class _ImportBase(_RecipientsBase):
    def setUp(self) -> None:
        super().setUp()
        self.issued = issue_token(
            self.org,
            self.admin,
            "sfg-import",
            operations=["promotion:read", "promotion:import"],
        )
        self.members = [
            guild_member(GUILD_ONLY_ID, days_ago=5),
            guild_member(SECOND_GUILD_ID, days_ago=5),
        ]

    def import_url(self, org: Organization | None = None) -> str:
        return (
            f"/api/organizations/{(org or self.org).pk}/integration/v1/"
            "contact-receipts/"
        )

    def version(self, event: Event | None = None) -> str:
        return authorized_event_subjects(self.org, event or self.event).mapping_version

    def subject(self, who: CustomUser | str) -> tuple[str | None, str | None, str]:
        if isinstance(who, str):
            return (None, None, who)
        who.refresh_from_db()
        ou = OrgUser.objects.filter(user=who, organization=self.org).first()
        assert who.discordId
        return (str(who.pk), str(ou.pk) if ou else None, who.discordId)

    def entry(
        self, source_id: int, who: CustomUser | str, **overrides: Any
    ) -> dict[str, Any]:
        user_id, org_user_id, discord_id = self.subject(who)
        event = overrides.pop("event", self.event)
        data = {
            "source_contact_id": str(source_id),
            "event_id": str(event.pk),
            "user_id": user_id,
            "org_user_id": org_user_id,
            "discord_id": discord_id,
            "recorded_at": RECORDED,
            "contact_method": "DISCORD_DM",
            "linkage": "occasion",
        }
        data.update(overrides)
        return data

    def post(
        self,
        entries: list[dict[str, Any]],
        *,
        version: str | None = None,
        event: Event | None = None,
        body: dict[str, Any] | None = None,
        raw: str | None = None,
        org: Organization | None = None,
    ):
        payload = body or {
            "source": "sfg",
            "mapping_version": version or self.version(event),
            "entries": entries,
        }
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
        """An account authorized as a recent guild joiner, with no OrgUser.

        (Playing an org tournament enrolls an OrgUser, so a non-member is
        reached through the guild source.)
        """
        user = self._user(name)
        self.members = [*self.members, guild_member(user.discordId, days_ago=3)]
        self.assertFalse(OrgUser.objects.filter(user=user).exists())
        return user


class ImportTests(_ImportBase):
    def test_new_contacts_apply_with_counts(self) -> None:
        body = self.imported(
            [self.entry(8021, self.recipient), self.entry(8022, GUILD_ONLY_ID)]
        )
        self.assertEqual(self.statuses(body), ["applied", "applied"])
        self.assertEqual(
            {k: v for k, v in body.items() if k != "results"},
            {"applied": 2, "unchanged": 0, "quarantined": 0, "association_updated": 0},
        )
        stored = self.receipt(8021)
        self.assertEqual(stored.user_id, self.recipient.pk)
        self.assertEqual(stored.association_state, AssociationState.LINKED)
        self.assertEqual(stored.recorded_at, datetime(2026, 11, 1, 10, tzinfo=UTC))
        guild_only = self.receipt(8022)
        self.assertIsNone(guild_only.user_id)
        self.assertEqual(guild_only.association_state, AssociationState.UNRESOLVED)

    def test_reordered_rescan_is_unchanged_with_original_import_time(self) -> None:
        first = [self.entry(8021, self.recipient), self.entry(8022, GUILD_ONLY_ID)]
        self.imported(first)
        before = {
            r.source_contact_id: (r.first_imported_at, r.source_hash)
            for r in ExternalPromotionReceipt.objects.all()
        }
        body = self.imported(list(reversed(first)))
        self.assertEqual(self.statuses(body), ["unchanged", "unchanged"])
        self.assertEqual(body["applied"], 0)
        self.assertEqual(body["unchanged"], 2)
        after = {
            r.source_contact_id: (r.first_imported_at, r.source_hash)
            for r in ExternalPromotionReceipt.objects.all()
        }
        self.assertEqual(before, after)

    def test_empty_batch_never_clears(self) -> None:
        self.imported([self.entry(8021, self.recipient)])
        body = self.imported([])
        self.assertEqual(
            body,
            {
                "results": [],
                "applied": 0,
                "unchanged": 0,
                "quarantined": 0,
                "association_updated": 0,
            },
        )
        self.assertTrue(self.ticked(self.recipient.discordId, self.recipient))

    def _assert_rejected(self, resp, status: int, code: str) -> None:
        self.assertError(resp, status, code)
        self.assertFalse(ExternalPromotionReceipt.objects.exists())

    def test_duplicate_source_ids_reject_whole_batch(self) -> None:
        resp = self.post(
            [self.entry(8021, self.recipient), self.entry(8021, GUILD_ONLY_ID)]
        )
        self._assert_rejected(resp, 400, "invalid_request")

    def test_bad_row_rejects_whole_batch(self) -> None:
        resp = self.post(
            [
                self.entry(8021, self.recipient),
                self.entry(8022, GUILD_ONLY_ID, recorded_at="2026-11-01 10:00"),
            ]
        )
        self._assert_rejected(resp, 400, "invalid_request")
        self.assertIn("entries[1].recorded_at", resp.json()["error"]["message"])

    def test_unauthorized_subject_rejects_whole_batch(self) -> None:
        stranger = self._user("stranger")
        resp = self.post([self.entry(8021, self.recipient), self.entry(8022, stranger)])
        self._assert_rejected(resp, 400, "invalid_request")

    def test_mismatched_tuple_rejects_whole_batch(self) -> None:
        wrong = self.entry(8022, self.recipient, user_id=None)
        resp = self.post([self.entry(8021, GUILD_ONLY_ID), wrong])
        self._assert_rejected(resp, 400, "invalid_request")

    def test_stale_mapping_version_rejects_whole_batch(self) -> None:
        stale = self.version()
        self.members = [*self.members, guild_member("990000000000000077", days_ago=1)]
        resp = self.post([self.entry(8021, self.recipient)], version=stale)
        self._assert_rejected(resp, 409, "mapping_changed")

    def test_source_id_collision_is_a_retryable_import_conflict(self) -> None:
        # A concurrent import stored one of these source IDs first, so the
        # insert fails after validation. That is not a mapping change.
        with patch(
            "org.integration.contacts._apply_entries",
            side_effect=IntegrityError("unique constraint"),
        ):
            resp = self.post([self.entry(8021, self.recipient)])
        self._assert_rejected(resp, 409, "import_conflict_retry")

    def test_guild_is_read_before_the_event_lock(self) -> None:
        lock = {"held": False}
        reads: list[bool] = []
        original = contacts.with_event_mutation

        def tracking(event_id: int, operation: Any) -> Any:
            lock["held"] = True
            try:
                return original(event_id, operation)
            finally:
                lock["held"] = False

        def fetch(**_: Any) -> list[dict]:
            reads.append(lock["held"])
            return list(self.members)

        version = self.version()
        with (
            patch.object(contacts, "with_event_mutation", tracking),
            patch(FETCH, side_effect=fetch),
        ):
            self.imported([self.entry(8021, GUILD_ONLY_ID)], version=version)
        self.assertEqual(reads, [False])

    def test_unavailable_guild_is_503_before_locking(self) -> None:
        version = self.version()
        with (
            patch(FETCH, side_effect=DiscordMembersFetchError("down")),
            patch.object(contacts, "with_event_mutation") as locked,
        ):
            resp = self.post([self.entry(8021, self.recipient)], version=version)
        self._assert_rejected(resp, 503, "subject_source_unavailable")
        locked.assert_not_called()

    def test_multiple_events_in_one_batch_rejected(self) -> None:
        resp = self.post(
            [
                self.entry(8021, self.recipient),
                self.entry(8022, self.recipient, event=self.completed_event),
            ]
        )
        self._assert_rejected(resp, 400, "invalid_request")

    def test_only_configured_occasion_linkage_and_source_methods(self) -> None:
        cases = {
            "linkage": "event_date",
            "contact_method": "EMAIL",
            "recorded_at": (timezone.now() + timedelta(minutes=10)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
        }
        for field, value in cases.items():
            with self.subTest(field=field):
                resp = self.post([self.entry(8021, self.recipient, **{field: value})])
                self._assert_rejected(resp, 400, "invalid_request")
        for method in ("DISCORD_DM", "DISCORD_GROUP_DM", "OTHER"):
            with self.subTest(method=method):
                source_id = 8100 + len(method)
                self.imported(
                    [self.entry(source_id, self.recipient, contact_method=method)]
                )

    def test_envelope_errors(self) -> None:
        version = self.version()
        entries = [self.entry(8021, self.recipient)]
        cases = [
            {"source": "draftforge", "mapping_version": version, "entries": entries},
            {"mapping_version": version, "entries": entries},
            {"source": "sfg", "mapping_version": version, "entries": entries, "x": 1},
            {"source": "sfg", "mapping_version": "8", "entries": entries},
            {
                "source": "sfg",
                "mapping_version": version,
                "entries": [{**entries[0], "note": "hi"}],
            },
        ]
        for body in cases:
            with self.subTest(body=sorted(body)):
                self._assert_rejected(self.post([], body=body), 400, "invalid_request")

    def test_unbound_event_and_wrong_org(self) -> None:
        unbound = Event.objects.create(
            organization=self.org,
            name="Unbound",
            scheduled_at=timezone.now() + timedelta(days=4),
            created_by=self.admin,
            state=EventState.UPCOMING,
        )
        resp = self.post(
            [self.entry(8021, self.recipient, event=unbound)], version="a" * 64
        )
        self._assert_rejected(resp, 403, "binding_missing")
        resp = self.post([self.entry(8021, self.recipient)], org=self.other_org)
        self._assert_rejected(resp, 404, "not_found")

    def test_replay_rechecks_grant_feature_and_binding(self) -> None:
        entries = [self.entry(8021, self.recipient)]
        self.imported(entries)
        read_only = issue_token(
            self.org, self.admin, "read-only", operations=["promotion:read"]
        )
        self.assertError(
            self.post(entries, raw=read_only.raw), 403, "operation_not_granted"
        )
        version = self.version()
        set_org_feature(self.org, FeatureKey.PROMOTION, enabled=False, actor=None)
        self.assertError(self.post(entries, version=version), 403, "feature_locked")
        set_org_feature(self.org, FeatureKey.PROMOTION, enabled=True, actor=None)
        with override_settings(SFG_PROMOTION_SYNC=bindings(self.org)):
            self.assertError(
                self.post(entries, version=version), 403, "binding_missing"
            )
        self.assertEqual(ExternalPromotionReceipt.objects.count(), 1)

    def _conflict_cases(self) -> dict[str, dict[str, Any]]:
        return {
            "recorded_at": {"recorded_at": "2026-11-02T10:00:00Z"},
            "contact_method": {"contact_method": "OTHER"},
            "discord_id": {"discord_id": SECOND_GUILD_ID},
        }

    def test_changed_source_facts_conflict_for_whole_batch(self) -> None:
        self.imported([self.entry(8021, GUILD_ONLY_ID)])
        original = self.receipt(8021)
        for name, change in self._conflict_cases().items():
            with self.subTest(changed=name):
                resp = self.post(
                    [
                        self.entry(8099, self.recipient),
                        self.entry(8021, GUILD_ONLY_ID, **change),
                    ]
                )
                self.assertError(resp, 409, "source_content_conflict")
                self.assertFalse(
                    ExternalPromotionReceipt.objects.filter(
                        source_contact_id=8099
                    ).exists()
                )
                stored = self.receipt(8021)
                self.assertEqual(stored.source_hash, original.source_hash)
                self.assertEqual(stored.recorded_at, original.recorded_at)
                self.assertEqual(stored.discord_id, GUILD_ONLY_ID)

    def test_changed_event_for_retained_source_id_conflicts(self) -> None:
        self.imported([self.entry(8021, self.recipient)])
        moved = self.entry(8021, self.recipient, event=self.completed_event)
        resp = self.post([moved], event=self.completed_event)
        self.assertError(resp, 409, "source_content_conflict")
        self.assertEqual(self.receipt(8021).event_id, self.event.pk)

    def test_two_source_ids_for_one_target_give_one_tick_and_nothing_else(
        self,
    ) -> None:
        users, org_users = CustomUser.objects.count(), OrgUser.objects.count()
        body = self.imported(
            [
                self.entry(8021, self.recipient),
                self.entry(8022, self.recipient, recorded_at="2026-11-03T10:00:00Z"),
                self.entry(8023, GUILD_ONLY_ID),
            ]
        )
        self.assertEqual(body["applied"], 3)
        contact = external_contact_for(
            self.event.pk, self.recipient.discordId, user_id=self.recipient.pk
        )
        self.assertEqual(
            contact,
            {
                "source": "sfg",
                "recorded_at": datetime(2026, 11, 3, 10, tzinfo=UTC),
                "delivery_verified": False,
                "can_undo": False,
            },
        )
        self.assertFalse(PromoSend.objects.exists())
        self.assertFalse(ContributionEntry.objects.nocache().exists())
        self.assertEqual(CustomUser.objects.count(), users)
        self.assertEqual(OrgUser.objects.count(), org_users)


class AssociationRescanTests(_ImportBase):
    """Association-only changes never conflict, and never block a new contact."""

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
            [self.entry(8021, resolved), self.entry(8030, self.recipient)]
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
        body = self.imported(
            [self.entry(8021, player), self.entry(8031, GUILD_ONLY_ID)]
        )
        self.assertEqual(self.statuses(body), ["unchanged", "applied"])
        self.assertEqual(body["association_updated"], 1)
        after = self._assert_enriched(8021, before)
        self.assertEqual(after.org_user_id, org_user.pk)
        self.assertTrue(self.ticked(player.discordId, player))

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

        body = self.imported([self.entry(8021, keep), self.entry(8032, GUILD_ONLY_ID)])
        self.assertEqual(self.statuses(body), ["unchanged", "applied"])
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
        new_owner = CustomUser.objects.create_user(
            username="new_owner", password="x", discordId=discord_id
        )
        body = self.imported(
            [self.entry(8021, new_owner), self.entry(8033, GUILD_ONLY_ID)]
        )
        self.assertEqual(self.statuses(body), ["quarantined", "applied"])
        self.assertEqual(body["quarantined"], 1)
        self.assertEqual(body["applied"], 1)
        self.assertEqual(body["association_updated"], 0)
        after = self.receipt(8021)
        self.assertEqual(after.association_state, AssociationState.QUARANTINED)
        self.assertEqual(
            after.association_reason, AssociationReason.DISCORD_OWNER_CHANGED
        )
        self.assertEqual(after.user_id, first_owner.pk)
        self.assertEqual(after.source_hash, before.source_hash)
        self.assertFalse(self.ticked(discord_id, new_owner))

        again = self.imported([self.entry(8021, new_owner)])
        self.assertEqual(self.statuses(again), ["quarantined"])

    def test_membership_of_another_user_quarantines(self) -> None:
        player = self.non_member_player("ou_player")
        self.imported([self.entry(8021, player)])
        stored = self.receipt(8021)
        other = OrgUser.objects.create(
            user=self._user("ou_other"), organization=self.org
        )
        from org.integration.contacts import reconcile_association

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
        self.assertIsNotNone(
            self.row(self.candidates(source="discord", days=90), GUILD_ONLY_ID)
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
                        "source": "sfg",
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
        with override_settings(SFG_PROMOTION_SYNC=bindings(self.other_org)):
            body = self.candidates(hide_messaged="false")
        self.assertEqual(
            body["contact_sync"],
            {"configured": False, "last_receipt_imported_at": None, "warning": None},
        )
        row = self.row(body, self.recipient.discordId)
        assert row is not None
        self.assertFalse(row["contact_recorded"])

    def test_quarantined_or_foreign_receipt_does_not_tick(self) -> None:
        self._import_all()
        ExternalPromotionReceipt.objects.filter(source_contact_id=8021).update(
            association_state=AssociationState.QUARANTINED
        )
        ExternalPromotionReceipt.objects.filter(source_contact_id=8022).update(
            user=self.joiner
        )
        body = self.candidates(source="recent", n=10)
        self.assertIsNotNone(self.row(body, self.recipient.discordId))
        body = self.candidates(source="active", days=90)
        self.assertIsNotNone(self.row(body, self.active_player.discordId))

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
        row = self.row(self.candidates(hide_messaged="false"), self.recipient.discordId)
        assert row is not None
        self.assertIsNone(row["last_messaged"])
        self.assertTrue(row["contact_recorded"])
        self.assertIsNotNone(row["external_contact"])
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
