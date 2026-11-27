from datetime import date, datetime, timedelta

from django.test import TestCase
from django.utils import timezone
from structlog.testing import capture_logs

from app.models import CustomUser
from discordbot import dm_ledger
from discordbot.dm_ledger import (
    DM_STALE_CLAIM_S,
    PERMANENT_DM_ERROR_CODES,
    ClaimResult,
    DMClaim,
    DMFinal,
    ErrorClass,
    LedgerConflict,
    LedgerNotFound,
)
from discordbot.models import DiscordDM, DMKind, DMStatus, DMSubject
from events.models import Event
from league.models import League
from lobby.models import GameLobby
from org.models import Organization
from tournament.models import Tournament


def _req(
    key: str = "k1",
    token: str = "tok-a",
    *,
    kind: DMKind = DMKind.SIGNUP_REMINDER,
    discord_user_id: str = "1001",
    **extra: object,
) -> DMClaim:
    return DMClaim(
        kind=kind,
        idempotency_key=key,
        claim_token=token,
        discord_user_id=discord_user_id,
        **extra,  # type: ignore[arg-type]
    )


class DMLedgerTestCase(TestCase):
    def setUp(self) -> None:
        self.now = timezone.now()

    def claim(self, req: DMClaim, now: datetime | None = None) -> ClaimResult:
        return dm_ledger.claim(req, now=now or self.now)

    def fail_delivery(
        self,
        result: ClaimResult,
        token: str,
        error_class: ErrorClass,
        *,
        error_code: int | None = None,
    ) -> DiscordDM:
        return dm_ledger.finalize(
            result.id,
            DMFinal(
                status=DMStatus.FAILED,
                error_class=error_class,
                http_status=403,
                error_code=error_code,
                error="nope",
            ),
            claim_token=token,
            now=self.now,
        )


class ClaimTests(DMLedgerTestCase):
    def test_constants(self) -> None:
        self.assertEqual(DM_STALE_CLAIM_S, 600)
        self.assertEqual(PERMANENT_DM_ERROR_CODES, frozenset({50007, 10013, 50278}))

    def test_claim_creates_pending(self) -> None:
        result = self.claim(_req())
        self.assertTrue(result.granted)
        self.assertTrue(result.created)
        self.assertEqual(result.status, DMStatus.PENDING)
        self.assertEqual(result.attempts, 1)
        row = DiscordDM.objects.get(pk=result.id)
        self.assertEqual(row.status, DMStatus.PENDING)
        self.assertEqual(row.claim_token, "tok-a")
        self.assertEqual(row.claimed_at, self.now)
        self.assertIsNone(row.finished_at)

    def test_duplicate_claim_not_granted(self) -> None:
        first = self.claim(_req())
        dm_ledger.finalize(
            first.id,
            DMFinal(status=DMStatus.SENT, discord_message_id="m1"),
            claim_token="tok-a",
            now=self.now,
        )
        second = self.claim(_req(token="tok-b"))
        self.assertFalse(second.granted)
        self.assertFalse(second.created)
        self.assertEqual(second.id, first.id)
        self.assertEqual(second.status, DMStatus.SENT)
        self.assertEqual(DiscordDM.objects.count(), 1)

    def test_retryable_failed_reclaimed_attempts_incremented(self) -> None:
        first = self.claim(_req())
        self.fail_delivery(first, "tok-a", "pre_send")
        later = self.now + timedelta(seconds=5)
        second = self.claim(_req(token="tok-b"), now=later)
        self.assertTrue(second.granted)
        self.assertFalse(second.created)
        self.assertEqual(second.id, first.id)
        self.assertEqual(second.attempts, 2)
        self.assertEqual(second.status, DMStatus.PENDING)
        row = DiscordDM.objects.get(pk=first.id)
        self.assertEqual(row.status, DMStatus.PENDING)
        self.assertEqual(row.claim_token, "tok-b")
        self.assertEqual(row.claimed_at, later)
        self.assertEqual(row.error, "")
        self.assertIsNone(row.error_code)
        self.assertIsNone(row.http_status)
        self.assertFalse(row.retryable)
        self.assertIsNone(row.finished_at)
        self.assertIsNone(row.send_started_at)

    def test_reclaim_refreshes_recipient_and_component_context(self) -> None:
        user = CustomUser.objects.create(username="relinked", discordId="1001")
        first = self.claim(
            _req(
                "k-relink",
                "tok-1",
                context={"discord_event_id": 1},
                has_components=True,
            )
        )
        self.fail_delivery(first, "tok-1", "pre_send")
        user.discordId = "2002"
        user.save(update_fields=["discordId"])
        second = self.claim(
            _req(
                "k-relink",
                "tok-1",
                discord_user_id="2002",
                context={"discord_event_id": 2},
                has_components=True,
            )
        )
        self.assertTrue(second.granted)
        row = DiscordDM.objects.get(pk=second.id)
        self.assertEqual(row.discord_user_id, "2002")
        self.assertEqual(row.recipient_id, user.pk)
        self.assertEqual(row.context["discord_event_id"], 2)
        dm_ledger.finalize(
            row.pk,
            DMFinal(status=DMStatus.SENT, discord_message_id="9001"),
            claim_token="tok-1",
            now=self.now,
        )
        dm_ledger.record_click(
            discord_message_id="9001", discord_user_id="2002", now=self.now
        )
        row.refresh_from_db()
        self.assertEqual(row.click_count, 1)

    def test_permanent_failed_not_reclaimable(self) -> None:
        first = self.claim(_req())
        row = self.fail_delivery(first, "tok-a", "permanent", error_code=50007)
        self.assertFalse(row.retryable)
        self.assertEqual(row.error_code, 50007)
        second = self.claim(_req(token="tok-b"))
        self.assertFalse(second.granted)
        self.assertEqual(second.status, DMStatus.FAILED)
        self.assertEqual(DiscordDM.objects.get(pk=first.id).attempts, 1)

    def test_permanent_code_never_retryable(self) -> None:
        first = self.claim(_req())
        row = self.fail_delivery(first, "tok-a", "pre_send", error_code=10013)
        self.assertFalse(row.retryable)

    def test_same_token_pending_regrant_same_id(self) -> None:
        first = self.claim(_req())
        second = self.claim(_req(), now=self.now + timedelta(seconds=30))
        self.assertTrue(second.granted)
        self.assertFalse(second.created)
        self.assertEqual(second.id, first.id)
        self.assertEqual(second.attempts, 1)
        self.assertEqual(DiscordDM.objects.get(pk=first.id).claimed_at, self.now)

    def test_other_token_pending_not_granted(self) -> None:
        first = self.claim(_req())
        second = self.claim(_req(token="tok-b"))
        self.assertFalse(second.granted)
        self.assertEqual(second.id, first.id)
        self.assertEqual(second.status, DMStatus.PENDING)
        self.assertEqual(DiscordDM.objects.get(pk=first.id).claim_token, "tok-a")

    def test_stale_unstarted_pending_reclaimable(self) -> None:
        first = self.claim(_req(), now=self.now - timedelta(seconds=601))
        second = self.claim(_req(token="tok-b"))
        self.assertTrue(second.granted)
        self.assertEqual(second.id, first.id)
        self.assertEqual(second.attempts, 2)
        row = DiscordDM.objects.get(pk=first.id)
        self.assertEqual(row.claim_token, "tok-b")
        self.assertEqual(row.claimed_at, self.now)

    def test_fresh_unstarted_pending_not_reclaimable(self) -> None:
        self.claim(_req(), now=self.now - timedelta(seconds=599))
        self.assertFalse(self.claim(_req(token="tok-b")).granted)

    def test_stale_started_pending_never_reclaimed(self) -> None:
        old = self.now - timedelta(days=2)
        first = self.claim(_req(), now=old)
        self.assertTrue(dm_ledger.mark_sending(first.id, claim_token="tok-a", now=old))
        second = self.claim(_req(token="tok-b"))
        self.assertFalse(second.granted)
        self.assertEqual(second.status, DMStatus.PENDING)
        self.assertEqual(DiscordDM.objects.get(pk=first.id).attempts, 1)

    def test_terminal_rows_not_reclaimable(self) -> None:
        terminal = [
            DMStatus.SENT,
            DMStatus.UNKNOWN,
            DMStatus.SKIPPED_TEST_MODE,
            DMStatus.SKIPPED_NO_DISCORD,
            DMStatus.SKIPPED_DISABLED,
        ]
        for status in terminal:
            with self.subTest(status=status):
                key = f"terminal:{status}"
                first = self.claim(_req(key))
                dm_ledger.finalize(
                    first.id,
                    DMFinal(status=status),
                    claim_token="tok-a",
                    now=self.now,
                )
                again = self.claim(
                    _req(key, token="tok-b"), now=self.now + timedelta(days=1)
                )
                self.assertFalse(again.granted)
                self.assertEqual(again.status, status)

    def test_skip_initial_status_is_terminal(self) -> None:
        result = self.claim(_req(initial_status=DMStatus.SKIPPED_TEST_MODE))
        self.assertTrue(result.granted)
        self.assertTrue(result.created)
        self.assertEqual(result.status, DMStatus.SKIPPED_TEST_MODE)
        row = DiscordDM.objects.get(pk=result.id)
        self.assertEqual(row.status, DMStatus.SKIPPED_TEST_MODE)
        self.assertEqual(row.finished_at, self.now)
        again = self.claim(
            _req(token="tok-b", initial_status=DMStatus.SKIPPED_TEST_MODE)
        )
        self.assertFalse(again.granted)

    def test_initial_status_must_be_skip(self) -> None:
        for status in (DMStatus.PENDING, DMStatus.SENT, DMStatus.FAILED):
            with self.subTest(status=status), self.assertRaises(ValueError):
                _req(initial_status=status)
        self.assertEqual(DiscordDM.objects.count(), 0)

    def test_context_unknown_key_rejected(self) -> None:
        cases: list[tuple[DMKind, dict[str, object]]] = [
            (DMKind.LOBBY_INFO, {"side": "radiant", "password": "hunter2"}),
            (DMKind.SIGNUP_REMINDER, {"content": "hello"}),
            (DMKind.TEST_NOTIFICATION, {"embed": {}}),
        ]
        for kind, context in cases:
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.claim(_req(f"ctx:{kind}", kind=kind, context=context))
        self.assertEqual(DiscordDM.objects.count(), 0)

    def test_context_stored_normalized(self) -> None:
        result = self.claim(_req(kind=DMKind.LOBBY_INFO, context={"side": "dire"}))
        self.assertEqual(DiscordDM.objects.get(pk=result.id).context, {"side": "dire"})


class RecipientTests(DMLedgerTestCase):
    def test_recipient_resolved_from_discord_id(self) -> None:
        user = CustomUser.objects.create_user(username="u", password="pw")
        user.discordId = "5555"
        user.save()
        result = self.claim(_req(discord_user_id="5555"))
        self.assertEqual(DiscordDM.objects.get(pk=result.id).recipient_id, user.pk)

    def test_unknown_discord_id_leaves_recipient_null(self) -> None:
        result = self.claim(_req(discord_user_id="999"))
        self.assertIsNone(DiscordDM.objects.get(pk=result.id).recipient_id)

    def test_recipient_mismatch_logs_warning_keeps_both(self) -> None:
        user = CustomUser.objects.create_user(username="u", password="pw")
        user.discordId = "5555"
        user.save()
        with capture_logs() as logs:
            result = self.claim(_req(discord_user_id="6666", recipient_user_id=user.pk))
        row = DiscordDM.objects.get(pk=result.id)
        self.assertEqual(row.recipient_id, user.pk)
        self.assertEqual(row.discord_user_id, "6666")
        warnings = [e for e in logs if e["log_level"] == "warning"]
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["system"], "discord")
        self.assertEqual(warnings[0]["subsystem"], "dm")
        self.assertEqual(warnings[0]["ledger_id"], row.pk)

    def test_recipient_without_discord_id_no_warning(self) -> None:
        user = CustomUser.objects.create_user(username="u", password="pw")
        with capture_logs() as logs:
            result = self.claim(_req(discord_user_id="", recipient_user_id=user.pk))
        self.assertEqual(DiscordDM.objects.get(pk=result.id).recipient_id, user.pk)
        self.assertFalse([e for e in logs if e["log_level"] == "warning"])


class OrgResolutionTests(DMLedgerTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.owner = CustomUser.objects.create_user(username="owner", password="pw")
        self.org = Organization.objects.create(name="Org", owner=self.owner)
        self.other_org = Organization.objects.create(name="Other", owner=self.owner)

    def _org_for(self, subject_type: DMSubject, subject_id: int) -> int | None:
        result = self.claim(
            _req(
                f"org:{subject_type}:{subject_id}",
                subject_type=subject_type,
                subject_id=subject_id,
            )
        )
        return DiscordDM.objects.get(pk=result.id).organization_id

    def test_org_resolved_per_subject(self) -> None:
        league = League.objects.create(organization=self.org, name="L")
        league_tournament = Tournament.objects.create(
            name="LT", date_played=date.today(), league=league
        )
        event_tournament = Tournament.objects.create(
            name="ET", date_played=date.today()
        )
        event = Event.objects.create(
            organization=self.other_org,
            name="E",
            scheduled_at=timezone.now(),
            created_by=self.owner,
            tournament=event_tournament,
        )
        league_game = league_tournament.games.create(round=1)
        league_lobby = GameLobby.objects.create(
            game=league_game, external_ref=f"game:{league_game.pk}"
        )
        event_game = event_tournament.games.create(round=1)
        event_lobby = GameLobby.objects.create(
            game=event_game, external_ref=f"game:{event_game.pk}"
        )
        orphan = Tournament.objects.create(name="O", date_played=date.today())
        cases: list[tuple[DMSubject, int, int | None]] = [
            (DMSubject.EVENT, event.pk, self.other_org.pk),
            (DMSubject.TOURNAMENT, league_tournament.pk, self.org.pk),
            (DMSubject.TOURNAMENT, event_tournament.pk, self.other_org.pk),
            (DMSubject.TOURNAMENT, orphan.pk, None),
            (DMSubject.GAME_LOBBY, league_lobby.pk, self.org.pk),
            (DMSubject.GAME_LOBBY, event_lobby.pk, self.other_org.pk),
            (DMSubject.EVENT, 987654, None),
        ]
        for subject_type, subject_id, expected in cases:
            with self.subTest(subject=subject_type, subject_id=subject_id):
                self.assertEqual(self._org_for(subject_type, subject_id), expected)

    def test_explicit_org_wins(self) -> None:
        event = Event.objects.create(
            organization=self.other_org,
            name="E",
            scheduled_at=timezone.now(),
            created_by=self.owner,
        )
        result = self.claim(
            _req(
                subject_type=DMSubject.EVENT,
                subject_id=event.pk,
                organization_id=self.org.pk,
            )
        )
        self.assertEqual(
            DiscordDM.objects.get(pk=result.id).organization_id, self.org.pk
        )


class MarkSendingTests(DMLedgerTestCase):
    def test_mark_sending_sets_started(self) -> None:
        result = self.claim(_req())
        self.assertTrue(
            dm_ledger.mark_sending(result.id, claim_token="tok-a", now=self.now)
        )
        self.assertEqual(DiscordDM.objects.get(pk=result.id).send_started_at, self.now)

    def test_mark_sending_token_mismatch_false(self) -> None:
        result = self.claim(_req())
        self.assertFalse(
            dm_ledger.mark_sending(result.id, claim_token="tok-b", now=self.now)
        )
        self.assertIsNone(DiscordDM.objects.get(pk=result.id).send_started_at)

    def test_mark_sending_not_pending_false(self) -> None:
        result = self.claim(_req())
        dm_ledger.finalize(
            result.id, DMFinal(status=DMStatus.SENT), claim_token="tok-a", now=self.now
        )
        self.assertFalse(
            dm_ledger.mark_sending(result.id, claim_token="tok-a", now=self.now)
        )

    def test_mark_sending_missing_row_false(self) -> None:
        self.assertFalse(dm_ledger.mark_sending(424242, claim_token="t", now=self.now))


class FinalizeTests(DMLedgerTestCase):
    def test_finalize_sent_sets_fields(self) -> None:
        result = self.claim(_req())
        row = dm_ledger.finalize(
            result.id,
            DMFinal(
                status=DMStatus.SENT,
                discord_channel_id="c1",
                discord_message_id="m1",
                http_status=200,
            ),
            claim_token="tok-a",
            now=self.now,
        )
        self.assertEqual(row.status, DMStatus.SENT)
        self.assertEqual(row.discord_channel_id, "c1")
        self.assertEqual(row.discord_message_id, "m1")
        self.assertEqual(row.http_status, 200)
        self.assertEqual(row.sent_at, self.now)
        self.assertEqual(row.finished_at, self.now)
        self.assertFalse(row.retryable)

    def test_finalize_only_from_pending(self) -> None:
        result = self.claim(_req())
        dm_ledger.finalize(
            result.id,
            DMFinal(status=DMStatus.UNKNOWN),
            claim_token="tok-a",
            now=self.now,
        )
        with self.assertRaises(LedgerConflict):
            dm_ledger.finalize(
                result.id,
                DMFinal(status=DMStatus.SENT),
                claim_token="tok-a",
                now=self.now,
            )
        self.assertEqual(DiscordDM.objects.get(pk=result.id).status, DMStatus.UNKNOWN)

    def test_finalize_token_mismatch_conflict(self) -> None:
        result = self.claim(_req())
        with self.assertRaises(LedgerConflict):
            dm_ledger.finalize(
                result.id,
                DMFinal(status=DMStatus.SENT),
                claim_token="tok-b",
                now=self.now,
            )
        self.assertEqual(DiscordDM.objects.get(pk=result.id).status, DMStatus.PENDING)

    def test_finalize_pending_outcome_rejected(self) -> None:
        result = self.claim(_req())
        with self.assertRaises(ValueError):
            dm_ledger.finalize(
                result.id,
                DMFinal(status=DMStatus.PENDING),
                claim_token="tok-a",
                now=self.now,
            )

    def test_finalize_missing_row_not_found(self) -> None:
        with self.assertRaises(LedgerNotFound):
            dm_ledger.finalize(
                424242, DMFinal(status=DMStatus.SENT), claim_token="t", now=self.now
            )

    def test_finalize_repeat_same_token_idempotent(self) -> None:
        result = self.claim(_req())
        outcome = DMFinal(status=DMStatus.SENT, discord_message_id="m1")
        first = dm_ledger.finalize(
            result.id, outcome, claim_token="tok-a", now=self.now
        )
        again = dm_ledger.finalize(
            result.id,
            outcome,
            claim_token="tok-a",
            now=self.now + timedelta(seconds=10),
        )
        self.assertEqual(again.pk, first.pk)
        self.assertEqual(again.finished_at, self.now)
        with self.assertRaises(LedgerConflict):
            dm_ledger.finalize(
                result.id,
                DMFinal(status=DMStatus.FAILED, error_class="pre_send"),
                claim_token="tok-a",
                now=self.now,
            )

    def test_finalize_truncates_error_to_300(self) -> None:
        result = self.claim(_req())
        row = dm_ledger.finalize(
            result.id,
            DMFinal(status=DMStatus.UNKNOWN, error="x" * 1000),
            claim_token="tok-a",
            now=self.now,
        )
        self.assertEqual(len(row.error), 300)
        row.refresh_from_db()
        self.assertEqual(len(row.error), 300)

    def test_retryable_from_error_class(self) -> None:
        cases: list[tuple[ErrorClass | None, bool]] = [
            ("pre_send", True),
            ("rate_limit_timeout", True),
            ("before_send_failed", True),
            ("permanent", False),
            (None, False),
        ]
        for error_class, retryable in cases:
            with self.subTest(error_class=error_class):
                result = self.claim(_req(f"retry:{error_class}"))
                row = dm_ledger.finalize(
                    result.id,
                    DMFinal(status=DMStatus.FAILED, error_class=error_class),
                    claim_token="tok-a",
                    now=self.now,
                )
                self.assertEqual(row.retryable, retryable)

    def test_error_class_ignored_for_unknown(self) -> None:
        result = self.claim(_req())
        row = dm_ledger.finalize(
            result.id,
            DMFinal(status=DMStatus.UNKNOWN, error_class="pre_send"),
            claim_token="tok-a",
            now=self.now,
        )
        self.assertFalse(row.retryable)


class ClickTests(DMLedgerTestCase):
    def _sent(self, key: str = "k1", message_id: str = "m1") -> DiscordDM:
        result = self.claim(_req(key))
        return dm_ledger.finalize(
            result.id,
            DMFinal(
                status=DMStatus.SENT,
                discord_channel_id="c1",
                discord_message_id=message_id,
            ),
            claim_token="tok-a",
            now=self.now,
        )

    def test_record_click_counters(self) -> None:
        self._sent()
        t1 = self.now + timedelta(minutes=1)
        t2 = self.now + timedelta(minutes=5)
        dm_ledger.record_click(discord_message_id="m1", discord_user_id="1001", now=t1)
        row = dm_ledger.record_click(
            discord_message_id="m1", discord_user_id="1001", now=t2
        )
        assert row is not None
        self.assertEqual(row.click_count, 2)
        self.assertEqual(row.first_clicked_at, t1)
        self.assertEqual(row.last_clicked_at, t2)

    def test_record_click_wrong_user_noop(self) -> None:
        self._sent()
        self.assertIsNone(
            dm_ledger.record_click(
                discord_message_id="m1", discord_user_id="2002", now=self.now
            )
        )
        self.assertIsNone(
            dm_ledger.record_click(
                discord_message_id="nope", discord_user_id="1001", now=self.now
            )
        )
        row = DiscordDM.objects.get(discord_message_id="m1")
        self.assertEqual(row.click_count, 0)
        self.assertIsNone(row.first_clicked_at)
