from datetime import timedelta

from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest
from django.test import RequestFactory
from django.utils import timezone as tz
from structlog.contextvars import bind_contextvars, clear_contextvars
from structlog.testing import capture_logs

from app.models import CustomUser
from events import ledger
from events.constants import ActorRole, SignupAction, SignupMeans, SignupStatus
from events.ledger import (
    PLACEMENT_ACTIONS,
    SignupActor,
    current_interaction_id,
    event_snapshot,
    is_placement,
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

    def test_placement_actions(self) -> None:
        self.assertEqual(
            PLACEMENT_ACTIONS,
            frozenset(
                {
                    SignupAction.STAFF_ADDED,
                    SignupAction.DEMOTED,
                    SignupAction.REINSTATED,
                    SignupAction.VOIDED_WITHDRAWAL,
                    SignupAction.TRANSFERRED_OUT,
                    SignupAction.TRANSFERRED_IN,
                    SignupAction.SWAPPED,
                }
            ),
        )

    def test_is_placement(self) -> None:
        for action in PLACEMENT_ACTIONS:
            with self.subTest(action=action):
                self.assertTrue(is_placement(action))
        self.assertTrue(
            is_placement(SignupAction.APPROVED, from_status=SignupStatus.WAITLISTED)
        )
        for from_status in (SignupStatus.RSVP, "pending", None):
            with self.subTest(from_status=from_status):
                self.assertFalse(
                    is_placement(SignupAction.APPROVED, from_status=from_status)
                )
        self.assertFalse(is_placement(SignupAction.REJECTED))
        self.assertFalse(is_placement(SignupAction.CONFIRMED))

    def test_reexports(self) -> None:
        self.assertIs(ledger.ActorRole, ActorRole)
        self.assertIs(ledger.SignupAction, SignupAction)
        self.assertIs(ledger.SignupMeans, SignupMeans)


class SignupActorBuildersTests(EventTestCase):
    def tearDown(self) -> None:
        clear_contextvars()

    def _request(self, user: CustomUser | AnonymousUser) -> HttpRequest:
        request = RequestFactory().post("/")
        request.user = user
        return request

    def test_system_actor_carries_correlation_id(self) -> None:
        actor = SignupActor.system(correlation_id="merge-abc")
        self.assertEqual(actor.correlation_id, "merge-abc")
        self.assertEqual(actor.role, ActorRole.SYSTEM)
        self.assertEqual(actor.means, SignupMeans.SYSTEM)
        self.assertIsNone(actor.user)
        self.assertFalse(actor.staff_power)

    def test_discord_actor_reads_bound_interaction_id(self) -> None:
        self.assertEqual(SignupActor.discord(self.user).correlation_id, "")
        bind_contextvars(interaction_id="123456789012345678")
        self.assertEqual(
            SignupActor.discord(self.user).correlation_id, "123456789012345678"
        )
        self.assertEqual(
            SignupActor.discord(
                self.user, correlation_id="reaction:1:2"
            ).correlation_id,
            "reaction:1:2",
        )

    def test_current_interaction_id_truncates_to_64(self) -> None:
        self.assertEqual(current_interaction_id(), "")
        bind_contextvars(interaction_id="9" * 80)
        self.assertEqual(current_interaction_id(), "9" * 64)

    def test_for_request_on_roles(self) -> None:
        cases: list[
            tuple[CustomUser | AnonymousUser, CustomUser, bool, ActorRole, bool]
        ] = [
            (self.admin, self.user, False, ActorRole.STAFF, False),
            (self.admin, self.user, True, ActorRole.STAFF, False),
            (self.admin, self.admin, True, ActorRole.MEMBER, True),
            (self.admin, self.admin, False, ActorRole.MEMBER, False),
            (self.user, self.user, True, ActorRole.MEMBER, False),
            (self.unrelated_user, self.user, False, ActorRole.MEMBER, False),
            (AnonymousUser(), self.user, False, ActorRole.MEMBER, False),
        ]
        for acting, subject, staff_only, role, staff_power in cases:
            with self.subTest(
                acting=str(acting), subject=subject.username, staff_only=staff_only
            ):
                actor = SignupActor.for_request_on(
                    self._request(acting), subject, self.event, staff_only=staff_only
                )
                self.assertEqual(actor.role, role)
                self.assertEqual(actor.staff_power, staff_power)
                self.assertEqual(actor.means, SignupMeans.WEB)
                self.assertEqual(actor.correlation_id, "")
                if acting.is_authenticated:
                    self.assertEqual(actor.user, acting)
                else:
                    self.assertIsNone(actor.user)

    def test_for_request_on_ignores_bound_interaction_id(self) -> None:
        bind_contextvars(interaction_id="123")
        actor = SignupActor.for_request_on(
            self._request(self.user), self.user, self.event
        )
        self.assertEqual(actor.correlation_id, "")


class RecordFallbackTests(EventTestCase):
    def setUp(self) -> None:
        self.signup = EventSignup.objects.create(event=self.event, user=self.user)

    def test_record_falls_back_to_actor_correlation_id(self) -> None:
        actor = SignupActor.system(correlation_id="x1")
        entry = record_signup_change(
            event=self.event,
            subject=self.user,
            actor=actor,
            action=SignupAction.PROMOTED,
        )
        entry.refresh_from_db()
        self.assertEqual(entry.correlation_id, "x1")
        explicit = record_signup_change(
            event=self.event,
            subject=self.user,
            actor=actor,
            action=SignupAction.PROMOTED,
            correlation_id="y2",
        )
        explicit.refresh_from_db()
        self.assertEqual(explicit.correlation_id, "y2")

    def test_record_marks_staff_power_without_mutating_snapshot(self) -> None:
        actor = SignupActor(
            user=self.admin,
            role=ActorRole.MEMBER,
            means=SignupMeans.WEB,
            staff_power=True,
        )
        after = snapshot(self.signup, extra={"fill_tier": 1})
        entry = record_signup_change(
            event=self.event,
            subject=self.admin,
            actor=actor,
            action=SignupAction.REINSTATED,
            signup=self.signup,
            after=after,
        )
        entry.refresh_from_db()
        self.assertIs(entry.after["extra"]["staff_power"], True)
        self.assertEqual(entry.after["extra"]["fill_tier"], 1)
        self.assertEqual(after.extra, {"fill_tier": 1})

        none_after = record_signup_change(
            event=self.event,
            subject=self.admin,
            actor=actor,
            action=SignupAction.WITHDREW,
            signup=self.signup,
        )
        none_after.refresh_from_db()
        self.assertIsNone(none_after.after)

    def test_record_without_staff_power_leaves_extra(self) -> None:
        entry = record_signup_change(
            event=self.event,
            subject=self.user,
            actor=SignupActor.discord(self.user),
            action=SignupAction.SIGNED_UP,
            signup=self.signup,
            after=snapshot(self.signup),
        )
        entry.refresh_from_db()
        self.assertEqual(entry.after["extra"], {})
