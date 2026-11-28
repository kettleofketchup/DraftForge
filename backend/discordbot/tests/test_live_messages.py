"""Persistence and fencing for refreshes of delivered Discord messages."""

from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.db import transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from discordbot import dm_ledger
from discordbot.live_messages import (
    EDIT_LEASE,
    claim_live_edit,
    finish_live_edit,
    invalidate_live_messages,
    invalidate_live_subjects,
    track_message,
)
from discordbot.models import DiscordDM, DMKind, DMStatus, DMSubject, LiveDiscordMessage
from discordbot.payloads import live_component_digest


@override_settings(TEST=False)
class LiveMessageTests(TestCase):
    def setUp(self):
        self.render = self.enterContext(
            patch("discordbot.live_renderers.render_live_message")
        )
        self.render.return_value = {
            "components": [{"type": 10, "content": "1 signed up"}]
        }

    def track(self, message_id="101", renderer="event_signup_reminder", subject_id=1):
        return track_message(
            renderer=renderer,
            subject_id=subject_id,
            channel_id="123",
            message_id=message_id,
        )

    def test_enrollment_uses_confirmed_send_hash_and_still_reconciles_drift(self):
        digest = live_component_digest(self.render.return_value["components"])
        track_message(
            renderer="event_signup_reminder",
            subject_id=1,
            channel_id="123",
            message_id="101",
            initial_digest=digest,
        )
        self.assertIsNone(claim_live_edit())
        reconciled = LiveDiscordMessage.objects.get(message_id="101")
        self.assertIsNone(reconciled.last_edited_at)
        self.assertEqual(reconciled.applied_revision, 1)
        track_message(
            renderer="event_signup_reminder",
            subject_id=1,
            channel_id="123",
            message_id="102",
            initial_digest=digest,
        )
        self.render.return_value = {
            "components": [{"type": 10, "content": "changed during send"}]
        }
        self.assertEqual(claim_live_edit()["message_id"], "102")

    def test_unknown_renderer_cannot_enroll(self):
        with self.assertRaisesRegex(ValueError, "unknown live message renderer"):
            self.track(renderer="misspelling")

    def test_same_receipt_is_idempotent_and_cannot_be_retargeted(self):
        row = self.track()
        invalidate_live_messages(row.renderer, row.subject_id)
        self.assertEqual(self.track().revision, 2)
        with self.assertRaises(ValueError):
            self.track(subject_id=9)
        with self.assertRaises(ValueError):
            self.track(message_id="test-fake-message-id")

    def test_bulk_invalidation_scopes_renderer_and_subject_and_rolls_back(self):
        self.enterContext(
            patch.dict("discordbot.live_renderers.RENDERERS", {"other": self.render})
        )
        a, b, c = (
            self.track(),
            self.track("102", subject_id=2),
            self.track("103", renderer="other"),
        )
        self.track("104", subject_id=3)
        selected = LiveDiscordMessage.objects.filter(pk__in=[a.pk, b.pk]).values_list(
            "subject_id", flat=True
        )
        self.assertEqual(invalidate_live_subjects(a.renderer, selected), 2)
        with transaction.atomic():
            invalidate_live_messages(a.renderer, 1)
            transaction.set_rollback(True)
        revisions = list(
            LiveDiscordMessage.objects.order_by("pk").values_list("revision", flat=True)
        )
        self.assertEqual(revisions, [2, 2, 1, 1])
        self.assertEqual(c.revision, 1)

    def test_change_during_patch_survives_ack_and_is_rendered_before_reclaim(self):
        row = self.track()
        first = claim_live_edit()
        self.assertEqual(first["message_id"], row.message_id)
        self.assertIsNone(claim_live_edit())
        for _ in range(2):
            invalidate_live_messages(row.renderer, row.subject_id)
        self.assertTrue(finish_live_edit(row.pk, first["token"], "edited"))
        row.refresh_from_db()
        self.assertEqual((row.revision, row.applied_revision), (3, 1))
        self.render.return_value = {
            "components": [{"type": 10, "content": "3 signed up"}]
        }
        last = claim_live_edit()
        self.assertEqual(last["payload"], self.render.return_value)
        self.assertTrue(finish_live_edit(row.pk, last["token"], "edited"))
        self.assertIsNone(claim_live_edit())
        row.refresh_from_db()
        self.assertEqual(row.applied_revision, 3)

    def test_noop_still_advances_revision_and_drains_next_row(self):
        row = self.track()
        first = claim_live_edit()
        finish_live_edit(row.pk, first["token"], "edited")
        row.refresh_from_db()
        edited_at = row.last_edited_at
        invalidate_live_messages(row.renderer, row.subject_id)
        other = self.track(message_id="102", subject_id=2)
        self.assertEqual(claim_live_edit()["id"], other.pk)
        row.refresh_from_db()
        self.assertEqual(row.applied_revision, 2)
        self.assertIsNone(row.next_attempt_at)
        self.assertEqual(row.last_edited_at, edited_at)

    def test_unchanged_components_during_edit_do_not_trigger_another_patch(self):
        row = self.track()
        claim = claim_live_edit()
        invalidate_live_messages(row.renderer, row.subject_id)
        self.assertTrue(finish_live_edit(row.pk, claim["token"], "edited"))
        row.refresh_from_db()
        edited_at = row.last_edited_at
        self.assertEqual(row.applied_revision, 1)
        self.assertIsNone(claim_live_edit())
        row.refresh_from_db()
        self.assertEqual(row.applied_revision, row.revision)
        self.assertEqual(row.last_edited_at, edited_at)
        self.assertIsNone(row.next_attempt_at)

    def test_uncertain_patch_reconciled_on_expired_lease_and_stale_ack_fenced(self):
        row = self.track()
        a = claim_live_edit()
        finish_live_edit(row.pk, a["token"], "edited")
        invalidate_live_messages(row.renderer, row.subject_id)
        initial = self.render.return_value
        self.render.return_value = {"components": [{"type": 10, "content": "now 2"}]}
        expired = claim_live_edit()
        LiveDiscordMessage.objects.filter(pk=row.pk).update(
            next_attempt_at=timezone.now() - EDIT_LEASE
        )
        # The abandoned worker might have delivered "now 2". Even if the source
        # changes back, issue a real PATCH before recording the new snapshot.
        self.render.return_value = initial
        invalidate_live_messages(row.renderer, row.subject_id)
        recovered = claim_live_edit()
        self.assertNotEqual(recovered["token"], expired["token"])
        self.assertEqual(recovered["payload"], initial)
        self.assertFalse(
            finish_live_edit(row.pk, expired["token"], "missing", error_code=10008)
        )
        self.assertTrue(finish_live_edit(row.pk, recovered["token"], "edited"))

    def test_late_success_from_expired_worker_triggers_a_corrective_patch(self):
        row = self.track()
        expired = claim_live_edit()
        LiveDiscordMessage.objects.filter(pk=row.pk).update(
            next_attempt_at=timezone.now() - EDIT_LEASE
        )
        self.render.return_value = {"components": [{"type": 10, "content": "latest"}]}
        current = claim_live_edit()
        self.assertFalse(finish_live_edit(row.pk, expired["token"], "edited"))
        self.assertTrue(finish_live_edit(row.pk, current["token"], "edited"))
        repair = claim_live_edit()
        self.assertEqual(repair["payload"], self.render.return_value)
        self.assertNotEqual(repair["token"], current["token"])
        self.assertTrue(finish_live_edit(row.pk, repair["token"], "edited"))
        self.assertIsNone(claim_live_edit())

    def test_late_success_while_rendering_unchanged_components_forces_repair(self):
        row = self.track()
        expired = claim_live_edit()
        LiveDiscordMessage.objects.filter(pk=row.pk).update(
            next_attempt_at=timezone.now() - EDIT_LEASE
        )
        self.render.return_value = {"components": [{"type": 10, "content": "latest"}]}
        current = claim_live_edit()
        self.assertTrue(finish_live_edit(row.pk, current["token"], "edited"))
        invalidate_live_messages(row.renderer, row.subject_id)

        def render_during_late_ack(*args):
            self.render.side_effect = None
            self.assertFalse(finish_live_edit(row.pk, expired["token"], "edited"))
            return self.render.return_value

        self.render.side_effect = render_during_late_ack
        repair = claim_live_edit()
        self.assertEqual(repair["payload"], current["payload"])
        self.assertTrue(finish_live_edit(row.pk, repair["token"], "edited"))
        self.assertIsNone(claim_live_edit())

    def test_retry_preserves_discord_delay_across_invalidations_and_other_work_continues(
        self,
    ):
        row = self.track()
        first = claim_live_edit()
        before = timezone.now()
        self.assertTrue(
            finish_live_edit(
                row.pk, first["token"], "retry", error_code=20028, retry_after=120.5
            )
        )
        row.refresh_from_db()
        deadline = row.next_attempt_at
        self.assertGreaterEqual(deadline, before + timedelta(seconds=120.5))
        invalidate_live_messages(row.renderer, row.subject_id)
        self.assertIsNone(claim_live_edit())
        row.refresh_from_db()
        self.assertEqual(row.next_attempt_at, deadline)
        self.assertEqual(row.error_code, 20028)
        other = self.track("102")
        self.assertEqual(claim_live_edit()["id"], other.pk)

    def test_nonexistent_subject_and_render_failure_do_not_block_later_deliveries(self):
        gone, temporary, ready = self.track(), self.track("102"), self.track("103")
        self.render.side_effect = [
            None,
            RuntimeError("database unavailable"),
            self.render.return_value,
        ]
        self.assertEqual(claim_live_edit()["id"], ready.pk)
        gone.refresh_from_db()
        temporary.refresh_from_db()
        self.assertEqual(gone.state, "source_gone")
        self.assertEqual(temporary.state, "active")
        self.assertGreater(temporary.next_attempt_at, timezone.now())

    def test_missing_address_is_never_requeued_and_receipt_survives(self):
        row = self.track()
        claim = claim_live_edit()
        self.assertFalse(finish_live_edit(row.pk, str(uuid4()), "missing"))
        self.assertTrue(
            finish_live_edit(row.pk, claim["token"], "missing", error_code=10008)
        )
        self.assertEqual(invalidate_live_messages(row.renderer, row.subject_id), 0)
        row.refresh_from_db()
        self.assertEqual((row.state, row.error_code), ("missing", 10008))
        self.assertIsNone(claim_live_edit())

    def test_blocked_edit_waits_for_relevant_change_and_then_retries(self):
        row = self.track()
        claim = claim_live_edit()
        self.assertTrue(
            finish_live_edit(row.pk, claim["token"], "blocked", error_code=50013)
        )
        self.assertIsNone(claim_live_edit())
        row.refresh_from_db()
        self.assertEqual((row.state, row.error_code), ("blocked", 50013))
        self.assertEqual(invalidate_live_messages(row.renderer, row.subject_id + 1), 0)
        self.assertEqual(invalidate_live_messages(row.renderer, row.subject_id), 1)
        self.assertEqual(claim_live_edit()["id"], row.pk)

    def test_blocked_old_revision_does_not_strand_an_in_flight_change(self):
        row = self.track()
        claim = claim_live_edit()
        invalidate_live_messages(row.renderer, row.subject_id)
        self.render.return_value = {
            "components": [{"type": 10, "content": "fixed layout"}]
        }
        self.assertTrue(
            finish_live_edit(row.pk, claim["token"], "blocked", error_code=50035)
        )
        retry = claim_live_edit()
        self.assertEqual(retry["payload"], self.render.return_value)
        self.assertTrue(finish_live_edit(row.pk, retry["token"], "edited"))
        self.assertIsNone(claim_live_edit())


class DeliveredDMEnrollmentTests(TestCase):
    def deliver(
        self,
        key,
        *,
        enrolled=True,
        status=DMStatus.SENT,
        message_id="100",
        channel_id="200",
        recipient="321",
    ):
        claim = dm_ledger.claim(
            dm_ledger.DMClaim(
                kind=DMKind.SIGNUP_REMINDER,
                idempotency_key=key,
                claim_token="claim",
                discord_user_id=recipient,
                subject_type=DMSubject.EVENT,
                subject_id=12,
                has_components=True,
                context={"live_v2": True} if enrolled else {},
            ),
            now=timezone.now(),
        )
        return dm_ledger.finalize(
            claim.id,
            dm_ledger.DMFinal(
                status=status,
                discord_channel_id=channel_id,
                discord_message_id=message_id,
            ),
            claim_token="claim",
            now=timezone.now(),
        )

    def test_only_opted_in_confirmed_deliveries_with_real_addresses_are_tracked(self):
        row = self.deliver("live")
        self.deliver("legacy", enrolled=False, message_id="101")
        self.deliver("skipped", status=DMStatus.SKIPPED_TEST_MODE, message_id="102")
        self.deliver("fake", message_id="test-fake-message-id")
        self.deliver("no-channel", message_id="103", channel_id="")
        records = list(
            LiveDiscordMessage.objects.values_list("dm_id", "subject_id", "renderer")
        )
        self.assertEqual(records, [(row.pk, 12, "event_signup_reminder")])
        self.assertEqual(DiscordDM.objects.count(), 5)

    @override_settings(
        TEST=True, TEST_DISCORD_USER_ID="321", DISCORD_BOT_TOKEN="unit-test-token"
    )
    def test_test_stack_never_claims_another_recipient_or_unverified_channel(self):
        self.deliver("other", recipient="999")
        allowed = self.deliver("target", message_id="101")
        track_message(
            renderer="event_signup_reminder",
            subject_id=12,
            message_id="103",
            channel_id="202",
        )
        with patch(
            "discordbot.live_renderers.render_live_message",
            return_value={"components": []},
        ):
            with override_settings(DISCORD_BOT_TOKEN=""):
                self.assertIsNone(claim_live_edit())
            self.assertIsNone(claim_live_edit(discord_user_id="999"))
            with override_settings(TEST=False):
                other_claim = claim_live_edit(discord_user_id="999")
                self.assertEqual(other_claim["message_id"], "100")
            claim = claim_live_edit(discord_user_id="321")
            self.assertEqual(claim["message_id"], allowed.discord_message_id)
            self.assertIsNone(claim_live_edit())
