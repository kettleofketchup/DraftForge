from collections.abc import Callable
from dataclasses import dataclass
from unittest import mock

from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.response import Response
from rest_framework.test import APIClient

from app.models import CustomUser
from events.constants import (
    ActorRole,
    EventState,
    SignupAction,
    SignupMeans,
    SignupStatus,
)
from events.ledger import SignupActor
from events.models import (
    Event,
    EventSignup,
    ReadyCheck,
    ReadyCheckEntry,
    RollCallMode,
    SignupLedgerEntry,
)
from events.ready_check import close_ready_check, confirm_ready, open_ready_check
from events.ready_check_constants import (
    ReadyCheckConfirmVia,
    ReadyCheckEntryState,
    ReadyCheckLowCompletionAction,
    ReadyCheckOutcome,
    ReadyCheckPhase,
)
from events.tests.base import EventTestCase

NOTIFY = "events.discord.dispatch.notify_signup_changed"
SERVICES_NOTIFY = "events.services.notify_signup_changed"

READY_CHECK_KEYS = {
    "id",
    "phase",
    "outcome",
    "mode",
    "completion_pct",
    "min_completion_pct",
    "low_completion_action",
    "counts",
    "opened_at",
    "escalated_at",
    "chased_at",
    "closed_at",
    "cancelled_at",
    "last_progress_at",
    "opened_by",
    "resolved_by",
    "resolve_reason",
    "entries",
}
ENTRY_KEYS = {
    "id",
    "signup_id",
    "user",
    "state",
    "confirmed_via",
    "confirmed_at",
    "nudged_at",
    "dropped_at",
}


@dataclass(frozen=True)
class Setup:
    event: Event
    method: str
    path: str
    body: dict[str, object]


class ReadyCheckApiTestCase(EventTestCase):
    def setUp(self) -> None:
        for target in (NOTIFY, SERVICES_NOTIFY):
            patcher = mock.patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.host = self.make_user()
        self.host.nickname = "HostNick"
        self.host.save()
        self.helper = self.make_user()
        self.staff_actor = SignupActor(
            user=self.admin, role=ActorRole.STAFF, means=SignupMeans.WEB
        )

    def _event(self, **overrides: object) -> Event:
        fields: dict[str, object] = {
            "host": self.host,
            "tournament_league": self.league,
        }
        fields.update(overrides)
        event = self.make_event(**fields)
        event.helpers.add(self.helper)
        return event

    def _signup(
        self, event: Event, status_: str = SignupStatus.APPROVED
    ) -> EventSignup:
        return EventSignup.objects.create(
            event=event, user=self.make_user(), status=status_
        )

    def _open(self, event: Event) -> ReadyCheck:
        with self.captureOnCommitCallbacks(execute=True):
            check = open_ready_check(event, actor=self.staff_actor).check
        event.refresh_from_db()
        return check

    def _request(
        self,
        user: CustomUser | None,
        method: str,
        path: str,
        body: dict[str, object] | None = None,
    ) -> Response:
        client = APIClient()
        client.force_authenticate(user=user)
        with self.captureOnCommitCallbacks(execute=True):
            if method == "get":
                return client.get(path)
            return client.post(path, body or {}, format="json")

    def _post(
        self, user: CustomUser | None, path: str, body: dict[str, object] | None = None
    ) -> Response:
        return self._request(user, "post", path, body)

    def _rc_path(self, event: Event, suffix: str = "") -> str:
        base = f"/api/events/{event.pk}/ready-check/"
        return f"{base}{suffix}/" if suffix else base

    def _entry(self, check: ReadyCheck, signup: EventSignup) -> ReadyCheckEntry:
        return ReadyCheckEntry.objects.get(ready_check=check, signup=signup)

    def _ledger_count(self, event: Event) -> int:
        return SignupLedgerEntry.objects.filter(event=event).count()


@override_settings(READY_CHECK_AUTOMATIC_LIVE=True)
class RoleMatrixTests(ReadyCheckApiTestCase):
    def _held_event(self) -> Event:
        event = self._event(
            roll_call_enabled=True,
            roll_call_mode=RollCallMode.AUTOMATIC,
            ready_check_low_completion_action=ReadyCheckLowCompletionAction.HOLD_FOR_STAFF,
            ready_check_min_completion_pct=70,
        )
        for _ in range(3):
            self._signup(event)
        self._open(event)
        with self.captureOnCommitCallbacks(execute=True):
            result = close_ready_check(event, actor=self.staff_actor)
        assert result.check is not None
        self.assertEqual(result.check.phase, ReadyCheckPhase.HELD)
        return event

    def _setup(self, endpoint: str) -> Setup:
        if endpoint == "open":
            event = self._event()
            self._signup(event)
            return Setup(event, "post", self._rc_path(event, "open"), {})
        if endpoint == "resolve":
            event = self._held_event()
            return Setup(
                event,
                "post",
                self._rc_path(event, "resolve"),
                {"apply_drops": False, "reason": "Everyone is here"},
            )
        event = self._event()
        target = self._signup(event)
        self._signup(event)
        self._open(event)
        if endpoint == "get":
            return Setup(event, "get", self._rc_path(event), {})
        if endpoint == "confirm":
            return Setup(
                event,
                "post",
                self._rc_path(event, "confirm"),
                {"user_id": target.user_id},
            )
        return Setup(event, "post", self._rc_path(event, endpoint), {})

    ENDPOINTS = ("get", "open", "escalate", "close", "resolve", "confirm")

    def _allowed_roles(self) -> dict[str, Callable[[Event], CustomUser]]:
        return {
            "org_staff": lambda _event: self.admin,
            "league_staff": lambda _event: self.league_staff,
            "host": lambda _event: self.host,
            "helper": lambda _event: self.helper,
        }

    def _denied_roles(self) -> dict[str, Callable[[Event], CustomUser]]:
        def member(event: Event) -> CustomUser:
            return EventSignup.objects.filter(event=event).first().user  # type: ignore[union-attr]

        def other_host(_event: Event) -> CustomUser:
            user = self.make_user()
            self.make_event(host=user)
            return user

        def other_helper(_event: Event) -> CustomUser:
            user = self.make_user()
            self.make_event().helpers.add(user)
            return user

        def promoter(_event: Event) -> CustomUser:
            user = self.make_user()
            self.org.promoters.add(user)
            return user

        def removed_helper(event: Event) -> CustomUser:
            user = self.make_user()
            event.helpers.add(user)
            event.helpers.remove(user)
            return user

        return {
            "member": member,
            "non_member": lambda _event: self.unrelated_user,
            "other_event_host": other_host,
            "other_event_helper": other_helper,
            "promoter": promoter,
            "removed_helper": removed_helper,
        }

    def test_allowed_roles_succeed_on_every_operator_endpoint(self) -> None:
        for endpoint in self.ENDPOINTS:
            for role, get_user in self._allowed_roles().items():
                with self.subTest(endpoint=endpoint, role=role):
                    setup = self._setup(endpoint)
                    resp = self._request(
                        get_user(setup.event), setup.method, setup.path, setup.body
                    )
                    self.assertEqual(resp.status_code, 200, resp.content)

    def test_denied_roles_get_403_on_every_operator_endpoint(self) -> None:
        for endpoint in self.ENDPOINTS:
            for role, get_user in self._denied_roles().items():
                with self.subTest(endpoint=endpoint, role=role):
                    setup = self._setup(endpoint)
                    user = get_user(setup.event)
                    before = self._ledger_count(setup.event)
                    resp = self._request(user, setup.method, setup.path, setup.body)
                    self.assertEqual(resp.status_code, 403, resp.content)
                    self.assertEqual(self._ledger_count(setup.event), before)

    def test_non_member_forbidden_on_operator_endpoints(self) -> None:
        for endpoint in self.ENDPOINTS:
            with self.subTest(endpoint=endpoint):
                setup = self._setup(endpoint)
                resp = self._request(
                    self.unrelated_user, setup.method, setup.path, setup.body
                )
                self.assertEqual(resp.status_code, 403, resp.content)

    def test_anonymous_is_refused_on_every_operator_endpoint(self) -> None:
        for endpoint in self.ENDPOINTS:
            with self.subTest(endpoint=endpoint):
                setup = self._setup(endpoint)
                before = self._ledger_count(setup.event)
                resp = self._request(None, setup.method, setup.path, setup.body)
                self.assertIn(resp.status_code, (401, 403), resp.content)
                self.assertEqual(self._ledger_count(setup.event), before)

    def test_anonymous_ready_is_refused(self) -> None:
        event = self._event()
        self._signup(event)
        self._open(event)
        resp = self._post(None, f"/api/events/{event.pk}/ready/")
        self.assertIn(resp.status_code, (401, 403), resp.content)


@override_settings(READY_CHECK_AUTOMATIC_LIVE=True)
class ResolveTests(ReadyCheckApiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.event = self._event(
            roll_call_enabled=True,
            roll_call_mode=RollCallMode.AUTOMATIC,
            ready_check_low_completion_action=ReadyCheckLowCompletionAction.HOLD_FOR_STAFF,
            ready_check_min_completion_pct=70,
        )
        self.signups = [self._signup(self.event) for _ in range(3)]
        self.check = self._open(self.event)
        with self.captureOnCommitCallbacks(execute=True):
            close_ready_check(self.event, actor=self.staff_actor)
        self.check.refresh_from_db()
        self.assertEqual(self.check.phase, ReadyCheckPhase.HELD)

    def _resolve(self, user: CustomUser, body: dict[str, object]) -> Response:
        return self._post(user, self._rc_path(self.event, "resolve"), body)

    def _assert_resolved_by(self, user: CustomUser) -> None:
        missing = self._resolve(user, {"apply_drops": True})
        self.assertEqual(missing.status_code, 400, missing.content)
        self.check.refresh_from_db()
        self.assertEqual(self.check.phase, ReadyCheckPhase.HELD)

        resp = self._resolve(
            user,
            {
                "apply_drops": True,
                "keep_signup_ids": [self.signups[0].pk],
                "reason": "  Two said they are late  ",
            },
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.check.refresh_from_db()
        self.assertEqual(self.check.phase, ReadyCheckPhase.CLOSED)
        self.assertEqual(self.check.outcome, ReadyCheckOutcome.STAFF_RESOLVED)
        self.assertEqual(self.check.resolved_by, user)
        self.assertEqual(self.check.resolve_reason, "Two said they are late")
        body = resp.json()
        self.assertEqual(body["ready_check"]["resolved_by"]["pk"], user.pk)
        self.assertTrue(body["changed"])
        self.assertEqual(
            sorted(body["dropped_user_ids"]),
            sorted(s.user_id for s in self.signups[1:]),
        )
        self.assertEqual(body["promoted_signup_ids"], [])

    def test_host_can_resolve_held_check_with_reason(self) -> None:
        self._assert_resolved_by(self.host)

    def test_helper_can_resolve_held_check_with_reason(self) -> None:
        self._assert_resolved_by(self.helper)

    def test_blank_reason_is_400(self) -> None:
        resp = self._resolve(self.admin, {"apply_drops": False, "reason": "   "})
        self.assertEqual(resp.status_code, 400, resp.content)
        self.check.refresh_from_db()
        self.assertEqual(self.check.phase, ReadyCheckPhase.HELD)

    def test_long_reason_is_400(self) -> None:
        resp = self._resolve(self.admin, {"apply_drops": False, "reason": "x" * 501})
        self.assertEqual(resp.status_code, 400, resp.content)
        ok = self._resolve(self.admin, {"apply_drops": False, "reason": "x" * 500})
        self.assertEqual(ok.status_code, 200, ok.content)

    def test_non_int_keep_ids_is_400(self) -> None:
        resp = self._resolve(
            self.admin,
            {"apply_drops": True, "keep_signup_ids": ["abc"], "reason": "ok"},
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.check.refresh_from_db()
        self.assertEqual(self.check.phase, ReadyCheckPhase.HELD)

    def test_unknown_keep_id_is_400(self) -> None:
        other = self._signup(self._event())
        resp = self._resolve(
            self.admin,
            {"apply_drops": True, "keep_signup_ids": [other.pk], "reason": "ok"},
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual(resp.json(), {"error": "Unknown signup in keep list."})

    def test_resolve_on_open_check_is_409_not_held(self) -> None:
        event = self._event()
        self._signup(event)
        self._open(event)
        resp = self._post(
            self.admin,
            self._rc_path(event, "resolve"),
            {"apply_drops": False, "reason": "ok"},
        )
        self.assertEqual(resp.status_code, 409, resp.content)
        self.assertEqual(resp.json()["code"], "not_held")

    def test_resolve_without_check_is_409_no_ready_check(self) -> None:
        event = self._event()
        resp = self._post(
            self.admin,
            self._rc_path(event, "resolve"),
            {"apply_drops": False, "reason": "ok"},
        )
        self.assertEqual(resp.status_code, 409, resp.content)
        self.assertEqual(resp.json()["code"], "no_ready_check")


class ConfirmTests(ReadyCheckApiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.event = self._event()
        self.member = self._signup(self.event)
        self.other = self._signup(self.event)
        self.check = self._open(self.event)

    def test_helper_confirm_on_behalf(self) -> None:
        resp = self._post(
            self.helper,
            self._rc_path(self.event, "confirm"),
            {"user_id": self.member.user_id},
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual(body["result"], "confirmed")
        self.assertEqual(set(body["entry"]), ENTRY_KEYS)
        self.assertEqual(body["entry"]["state"], ReadyCheckEntryState.CONFIRMED)
        self.assertEqual(body["entry"]["confirmed_via"], ReadyCheckConfirmVia.STAFF)
        entry = self._entry(self.check, self.member)
        self.assertEqual(entry.state, ReadyCheckEntryState.CONFIRMED)
        self.assertEqual(entry.confirmed_via, ReadyCheckConfirmVia.STAFF)
        row = SignupLedgerEntry.objects.get(
            event=self.event,
            action=SignupAction.CONFIRMED,
            correlation_id=f"rc{self.check.pk}:confirm",
        )
        self.assertEqual(row.actor_user, self.helper)
        self.assertEqual(row.subject_user_id, self.member.user_id)
        self.assertTrue(row.on_behalf)

        again = self._post(
            self.helper,
            self._rc_path(self.event, "confirm"),
            {"user_id": self.member.user_id},
        )
        self.assertEqual(again.status_code, 200, again.content)
        self.assertEqual(again.json()["result"], "already_confirmed")

    def test_member_ready_ignores_body_user_id(self) -> None:
        resp = self._post(
            self.member.user,
            f"/api/events/{self.event.pk}/ready/",
            {"user_id": self.other.user_id},
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["result"], "confirmed")
        self.assertEqual(resp.json()["entry"]["user"]["pk"], self.member.user_id)
        self.assertEqual(
            self._entry(self.check, self.member).state, ReadyCheckEntryState.CONFIRMED
        )
        self.assertEqual(
            self._entry(self.check, self.member).confirmed_via, ReadyCheckConfirmVia.WEB
        )
        self.assertEqual(
            self._entry(self.check, self.other).state, ReadyCheckEntryState.PENDING
        )
        row = SignupLedgerEntry.objects.get(
            event=self.event, action=SignupAction.CONFIRMED
        )
        self.assertFalse(row.on_behalf)

    def test_member_cannot_confirm_on_behalf(self) -> None:
        resp = self._post(
            self.member.user,
            self._rc_path(self.event, "confirm"),
            {"user_id": self.other.user_id},
        )
        self.assertEqual(resp.status_code, 403, resp.content)
        self.assertEqual(
            self._entry(self.check, self.other).state, ReadyCheckEntryState.PENDING
        )

    def test_ready_not_in_check_is_409(self) -> None:
        resp = self._post(self.unrelated_user, f"/api/events/{self.event.pk}/ready/")
        self.assertEqual(resp.status_code, 409, resp.content)
        body = resp.json()
        self.assertEqual(body["code"], "not_in_check")
        self.assertEqual(body["host"]["pk"], self.host.pk)

    def test_confirm_unknown_user_is_409_not_in_check(self) -> None:
        resp = self._post(
            self.admin, self._rc_path(self.event, "confirm"), {"user_id": 999999}
        )
        self.assertEqual(resp.status_code, 409, resp.content)
        self.assertEqual(resp.json()["code"], "not_in_check")

    def test_confirm_without_user_id_is_400(self) -> None:
        resp = self._post(self.admin, self._rc_path(self.event, "confirm"), {})
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_ready_without_check_is_409_no_ready_check(self) -> None:
        event = self._event()
        signup = self._signup(event)
        resp = self._post(signup.user, f"/api/events/{event.pk}/ready/")
        self.assertEqual(resp.status_code, 409, resp.content)
        body = resp.json()
        self.assertEqual(body["code"], "no_ready_check")
        self.assertEqual(body["host"]["pk"], self.host.pk)

    def test_ready_on_unknown_event_is_404(self) -> None:
        resp = self._post(self.member.user, "/api/events/999999/ready/")
        self.assertEqual(resp.status_code, 404, resp.content)

    def test_ready_on_event_outside_filtered_queryset_is_404(self) -> None:
        resp = self._post(
            self.member.user,
            f"/api/events/{self.event.pk}/ready/?organization=999999",
        )
        self.assertEqual(resp.status_code, 404, resp.content)
        self.assertEqual(
            self._entry(self.check, self.member).state, ReadyCheckEntryState.PENDING
        )


@override_settings(READY_CHECK_AUTOMATIC_LIVE=True)
class ClosedConfirmTests(ReadyCheckApiTestCase):
    def test_dropped_member_ready_is_409_with_host(self) -> None:
        event = self._event(
            roll_call_enabled=True,
            roll_call_mode=RollCallMode.AUTOMATIC,
            ready_check_min_completion_pct=70,
        )
        signups = [self._signup(event) for _ in range(4)]
        self._open(event)
        for signup in signups[:3]:
            with self.captureOnCommitCallbacks(execute=True):
                confirm_ready(
                    event,
                    signup.user,
                    via=ReadyCheckConfirmVia.WEB,
                    actor=SignupActor(
                        user=signup.user, role=ActorRole.MEMBER, means=SignupMeans.WEB
                    ),
                )
        with self.captureOnCommitCallbacks(execute=True):
            result = close_ready_check(event, actor=self.staff_actor)
        assert result.check is not None
        self.assertEqual(result.check.outcome, ReadyCheckOutcome.BINDING)
        dropped = signups[3]
        self.assertEqual(
            EventSignup.objects.nocache().get(pk=dropped.pk).status,
            SignupStatus.DROPPED,
        )
        before = self._ledger_count(event)

        resp = self._post(dropped.user, f"/api/events/{event.pk}/ready/")
        self.assertEqual(resp.status_code, 409, resp.content)
        body = resp.json()
        self.assertEqual(body["code"], "ready_check_closed")
        self.assertIn("HostNick", body["error"])
        self.assertIn(event.name, body["error"])
        self.assertEqual(body["host"]["pk"], self.host.pk)
        self.assertEqual(self._ledger_count(event), before)


class EscalateCloseTests(ReadyCheckApiTestCase):
    def test_escalate_and_close_without_check_are_409(self) -> None:
        event = self._event()
        for suffix in ("escalate", "close"):
            with self.subTest(suffix=suffix):
                resp = self._post(self.admin, self._rc_path(event, suffix))
                self.assertEqual(resp.status_code, 409, resp.content)
                self.assertEqual(resp.json()["code"], "no_ready_check")
                self.assertIn("error", resp.json())

    def test_escalate_reports_changed_once(self) -> None:
        event = self._event()
        self._signup(event)
        self._open(event)
        first = self._post(self.host, self._rc_path(event, "escalate"))
        self.assertEqual(first.status_code, 200, first.content)
        self.assertTrue(first.json()["changed"])
        self.assertEqual(
            first.json()["ready_check"]["phase"], ReadyCheckPhase.ESCALATED
        )
        second = self._post(self.host, self._rc_path(event, "escalate"))
        self.assertEqual(second.status_code, 200, second.content)
        self.assertFalse(second.json()["changed"])

    def test_manual_close_drops_nobody(self) -> None:
        event = self._event()
        signups = [self._signup(event) for _ in range(2)]
        self._open(event)
        resp = self._post(self.helper, self._rc_path(event, "close"))
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertTrue(body["changed"])
        self.assertEqual(body["dropped_user_ids"], [])
        self.assertEqual(body["promoted_signup_ids"], [])
        self.assertEqual(body["ready_check"]["phase"], ReadyCheckPhase.CLOSED)
        self.assertEqual(
            body["ready_check"]["outcome"], ReadyCheckOutcome.STAFF_VERIFIED
        )
        for signup in signups:
            self.assertEqual(
                EventSignup.objects.nocache().get(pk=signup.pk).status,
                SignupStatus.APPROVED,
            )
        again = self._post(self.helper, self._rc_path(event, "close"))
        self.assertEqual(again.status_code, 200, again.content)
        self.assertFalse(again.json()["changed"])

    def test_open_returns_check_and_event(self) -> None:
        event = self._event()
        self._signup(event)
        resp = self._post(self.host, self._rc_path(event, "open"))
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertTrue(body["created"])
        self.assertEqual(body["event"]["id"], event.pk)
        self.assertEqual(body["event"]["state"], EventState.ROLL_CALL)
        self.assertEqual(body["ready_check"]["opened_by"]["pk"], self.host.pk)
        again = self._post(self.host, self._rc_path(event, "open"))
        self.assertEqual(again.status_code, 200, again.content)
        self.assertFalse(again.json()["created"])
        self.assertEqual(again.json()["ready_check"]["id"], body["ready_check"]["id"])

    def test_open_refused_is_400(self) -> None:
        event = self._event(state=EventState.UPCOMING)
        resp = self._post(self.admin, self._rc_path(event, "open"))
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("error", resp.json())
        self.assertFalse(ReadyCheck.objects.filter(event=event).exists())


class CompletionTests(ReadyCheckApiTestCase):
    def test_ready_and_close_after_completion_change_nothing(self) -> None:
        event = self._event()
        member = self._signup(event)
        self._open(event)
        complete = self._post(self.admin, f"/api/events/{event.pk}/complete/")
        self.assertEqual(complete.status_code, 200, complete.content)
        event.refresh_from_db()
        roster_before = (
            set(event.tournament.users.values_list("pk", flat=True))
            if event.tournament_id
            else set()
        )
        ledger_before = self._ledger_count(event)

        ready = self._post(member.user, f"/api/events/{event.pk}/ready/")
        self.assertEqual(ready.status_code, 409, ready.content)
        self.assertEqual(ready.json()["code"], "no_ready_check")
        close = self._post(self.host, self._rc_path(event, "close"))
        self.assertEqual(close.status_code, 409, close.content)
        self.assertEqual(close.json()["code"], "no_ready_check")

        event.refresh_from_db()
        roster_after = (
            set(event.tournament.users.values_list("pk", flat=True))
            if event.tournament_id
            else set()
        )
        self.assertEqual(self._ledger_count(event), ledger_before)
        self.assertEqual(roster_after, roster_before)
        self.assertEqual(
            EventSignup.objects.nocache().get(pk=member.pk).status,
            SignupStatus.APPROVED,
        )


class PayloadTests(ReadyCheckApiTestCase):
    def test_get_without_check_returns_null(self) -> None:
        event = self._event()
        resp = self._request(self.host, "get", self._rc_path(event))
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json(), {"ready_check": None})

    def test_payload_shape_and_counts(self) -> None:
        event = self._event()
        signups = [self._signup(event) for _ in range(5)]
        check = self._open(event)
        with self.captureOnCommitCallbacks(execute=True):
            confirm_ready(
                event,
                signups[0].user,
                via=ReadyCheckConfirmVia.WEB,
                actor=SignupActor(
                    user=signups[0].user, role=ActorRole.MEMBER, means=SignupMeans.WEB
                ),
            )
        ReadyCheckEntry.objects.filter(ready_check=check, signup=signups[1]).update(
            state=ReadyCheckEntryState.DROPPED
        )
        ReadyCheckEntry.objects.filter(ready_check=check, signup=signups[2]).update(
            state=ReadyCheckEntryState.EXCUSED
        )
        deleted_user_id = signups[4].user_id
        EventSignup.objects.filter(pk=signups[4].pk).delete()

        resp = self._request(self.helper, "get", self._rc_path(event))
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()["ready_check"]
        self.assertEqual(set(data), READY_CHECK_KEYS)
        self.assertEqual(
            data["counts"],
            {"asked": 5, "pending": 2, "confirmed": 1, "dropped": 1, "excused": 1},
        )
        self.assertEqual(data["mode"], RollCallMode.MANUAL)
        self.assertEqual(data["min_completion_pct"], 70)
        self.assertEqual(
            data["low_completion_action"],
            check.settings_snapshot["ready_check_low_completion_action"],
        )
        self.assertEqual(data["opened_by"]["pk"], self.admin.pk)
        self.assertIsNone(data["resolved_by"])
        for entry in data["entries"]:
            self.assertEqual(set(entry), ENTRY_KEYS)
            self.assertNotIn("discordId", entry["user"])
        orphan = next(e for e in data["entries"] if e["user"]["pk"] == deleted_user_id)
        self.assertIsNone(orphan["signup_id"])

    def _get_query_count(self, entries: int) -> int:
        event = self._event()
        for _ in range(entries):
            self._signup(event)
        self._open(event)
        path = self._rc_path(event)
        self._request(self.host, "get", path)
        with CaptureQueriesContext(connection) as ctx:
            resp = self._request(self.host, "get", path)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(len(resp.json()["ready_check"]["entries"]), entries)
        return len(ctx.captured_queries)

    def test_query_count_does_not_grow_with_entries(self) -> None:
        self.assertEqual(self._get_query_count(2), self._get_query_count(20))
