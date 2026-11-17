from datetime import timedelta

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from django.utils import timezone as tz
from structlog.testing import capture_logs

from events import ledger
from events.constants import ActorRole, SignupAction, SignupMeans, SignupStatus
from events.ledger import (
    PLACEMENT_ACTIONS,
    SignupActor,
    event_snapshot,
    record_signup_change,
    snapshot,
    user_snapshot,
)
from events.models import EventSignup, SignupLedgerEntry
from events.schemas import SignupSnapshot
from events.tests.base import EventTestCase


class RecordSignupChangeTest(EventTestCase):
    def setUp(self) -> None:
        self.signup = EventSignup.objects.create(event=self.event, user=self.user)

    def test_record_sets_fields(self) -> None:
        before = snapshot(self.signup)
        self.signup.status = SignupStatus.CANCELLED
        after = snapshot(self.signup)
        request = RequestFactory().post("/")
        request.user = self.admin
        entry = record_signup_change(
            event=self.event,
            subject=self.user,
            actor=SignupActor.from_request(request, role=ActorRole.STAFF),
            action=SignupAction.WITHDREW,
            signup=self.signup,
            before=before,
            after=after,
            reason="staff cleanup",
            rules_overridden=["x"],
        )
        entry.refresh_from_db()
        self.assertEqual(entry.actor_role, "staff")
        self.assertEqual(entry.means, "web")
        self.assertTrue(entry.on_behalf)
        self.assertEqual(entry.organization_id, self.event.organization_id)
        self.assertEqual(entry.event_id, self.event.pk)
        self.assertEqual(entry.signup_id, self.signup.pk)
        self.assertEqual(entry.action, "withdrew")
        self.assertEqual(entry.before, before.model_dump(mode="json"))
        self.assertEqual(entry.after, after.model_dump(mode="json"))
        self.assertEqual(entry.after["status"], "cancelled")
        self.assertEqual(entry.rules_overridden, ["x"])
        self.assertEqual(entry.reason, "staff cleanup")
        self.assertEqual(entry.actor_user_id, self.admin.pk)
        self.assertEqual(entry.actor_snapshot["user_id"], self.admin.pk)
        self.assertEqual(entry.subject_user_id, self.user.pk)
        self.assertEqual(entry.subject_snapshot["user_id"], self.user.pk)
        self.assertEqual(entry.event_snapshot["id"], self.event.pk)

    def test_self_action_not_on_behalf(self) -> None:
        entry = record_signup_change(
            event=self.event,
            subject=self.user,
            actor=SignupActor.discord(self.user),
            action=SignupAction.SIGNED_UP,
            signup=self.signup,
            after=snapshot(self.signup),
        )
        self.assertFalse(entry.on_behalf)
        self.assertEqual(entry.means, "discord_button")
        self.assertEqual(entry.actor_role, "member")
        self.assertIsNone(entry.before)

    def test_system_actor(self) -> None:
        entry = record_signup_change(
            event=self.event,
            subject=self.user,
            actor=SignupActor.system(),
            action=SignupAction.PROMOTED,
        )
        entry.refresh_from_db()
        self.assertIsNone(entry.actor_user)
        self.assertIsNone(entry.actor_snapshot)
        self.assertFalse(entry.on_behalf)
        self.assertEqual(entry.actor_role, "system")
        self.assertEqual(entry.means, "system")
        self.assertIsNone(entry.signup_id)
        self.assertEqual(entry.rules_overridden, [])

    def test_on_commit_log(self) -> None:
        with (
            capture_logs() as logs,
            self.captureOnCommitCallbacks(execute=True) as callbacks,
        ):
            entry = record_signup_change(
                event=self.event,
                subject=self.user,
                actor=SignupActor.discord(
                    self.admin, means=SignupMeans.DISCORD_REACTION
                ),
                action=SignupAction.SIGNED_UP,
                signup=self.signup,
                correlation_id="corr-1",
            )
            pre_commit = [
                e for e in logs if e["event"] == "signup_ledger_entry_recorded"
            ]
            self.assertEqual(pre_commit, [])
        self.assertEqual(len(callbacks), 1)
        recorded = [e for e in logs if e["event"] == "signup_ledger_entry_recorded"]
        self.assertEqual(len(recorded), 1)
        record = recorded[0]
        self.assertEqual(record["system"], "events")
        self.assertEqual(record["subsystem"], "ledger")
        self.assertEqual(record["log_level"], "info")
        self.assertEqual(
            {k: record[k] for k in record if k not in {"event", "log_level"}},
            {
                "system": "events",
                "subsystem": "ledger",
                "entry_id": entry.pk,
                "event_id": self.event.pk,
                "signup_id": self.signup.pk,
                "subject_user_id": self.user.pk,
                "actor_user_id": self.admin.pk,
                "actor_role": "member",
                "means": "discord_reaction",
                "action": "signed_up",
                "correlation_id": "corr-1",
            },
        )

    def test_caused_by_and_correlation(self) -> None:
        cause = record_signup_change(
            event=self.event,
            subject=self.user,
            actor=SignupActor.system(),
            action=SignupAction.WITHDREW,
            correlation_id="chain-1",
        )
        occurred = tz.now() - timedelta(hours=1)
        effect = record_signup_change(
            event=self.event,
            subject=self.admin,
            actor=SignupActor.system(),
            action=SignupAction.PROMOTED,
            caused_by=cause,
            correlation_id="chain-1",
            occurred_at=occurred,
        )
        effect.refresh_from_db()
        self.assertEqual(effect.caused_by_id, cause.pk)
        self.assertEqual(effect.correlation_id, "chain-1")
        self.assertEqual(effect.occurred_at, occurred)
        self.assertEqual(list(cause.effects.values_list("pk", flat=True)), [effect.pk])
        self.assertEqual(
            SignupLedgerEntry.objects.filter(correlation_id="chain-1").count(), 2
        )


class SnapshotTest(EventTestCase):
    def test_snapshot_round_trip(self) -> None:
        signup = EventSignup.objects.create(event=self.event, user=self.user)
        snap = snapshot(signup)
        self.assertEqual(
            SignupSnapshot.model_validate(snap.model_dump(mode="json")), snap
        )
        self.assertEqual(snap.status, signup.status)
        self.assertEqual(snap.commitment, signup.commitment)
        self.assertEqual(snap.rsvp_class, signup.rsvp_class)
        self.assertEqual(snap.line_seq, signup.line_seq)
        self.assertEqual(snap.signed_up_at, signup.signed_up_at)
        self.assertEqual(snap.waitlist_position, signup.waitlist_position)
        self.assertEqual(snap.event_team_id, signup.event_team_id)
        self.assertEqual(snap.extra, {})

        extra = snapshot(signup, extra={"fill_tier": 1})
        self.assertEqual(extra.extra, {"fill_tier": 1})
        self.assertEqual(
            SignupSnapshot.model_validate(extra.model_dump(mode="json")), extra
        )

    def test_user_snapshot_nickname(self) -> None:
        self.assertEqual(
            user_snapshot(self.user),
            {
                "user_id": self.user.pk,
                "username": self.user.username,
                "nickname": "EventUser",
                "discord_id": self.user.discordId,
            },
        )
        self.assertIsNone(user_snapshot(None))

    def test_event_snapshot_keys(self) -> None:
        snap = event_snapshot(self.event)
        self.assertEqual(
            set(snap),
            {
                "id",
                "name",
                "scheduled_at",
                "ends_at",
                "state",
                "organization_id",
                "series_id",
                "tournament_id",
            },
        )
        self.assertEqual(snap["series_id"], self.event.event_repeater_id)
        self.assertEqual(snap["scheduled_at"], self.event.scheduled_at.isoformat())
        self.assertIsNone(snap["ends_at"])
        self.assertEqual(snap["state"], self.event.state)
        self.assertEqual(snap["organization_id"], self.org.pk)

    def test_event_snapshot_ends_at_iso(self) -> None:
        self.event.ends_at = self.event.scheduled_at + timedelta(hours=2)
        self.assertEqual(
            event_snapshot(self.event)["ends_at"], self.event.ends_at.isoformat()
        )


class ActorTest(EventTestCase):
    def test_from_request_anonymous(self) -> None:
        request = RequestFactory().get("/")
        request.user = AnonymousUser()
        actor = SignupActor.from_request(request)
        self.assertIsNone(actor.user)
        self.assertEqual(actor.role, ActorRole.MEMBER)
        self.assertEqual(actor.means, SignupMeans.WEB)

    def test_from_request_authenticated(self) -> None:
        request = RequestFactory().get("/")
        request.user = self.user
        actor = SignupActor.from_request(request)
        self.assertEqual(actor.user, self.user)
        self.assertEqual(actor.means, SignupMeans.WEB)

    def test_system(self) -> None:
        actor = SignupActor.system()
        self.assertIsNone(actor.user)
        self.assertEqual(actor.role, ActorRole.SYSTEM)
        self.assertEqual(actor.means, SignupMeans.SYSTEM)

    def test_placement_actions_empty(self) -> None:
        self.assertEqual(PLACEMENT_ACTIONS, frozenset())

    def test_reexports(self) -> None:
        self.assertIs(ledger.ActorRole, ActorRole)
        self.assertIs(ledger.SignupAction, SignupAction)
        self.assertIs(ledger.SignupMeans, SignupMeans)
