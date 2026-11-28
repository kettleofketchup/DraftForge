from datetime import timedelta
from unittest.mock import patch

import requests
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from app import internal_client
from discordbot.models import (
    DiscordEventMsgSignup,
    DiscordMessageLog,
    SignupDeliveryStatus,
    SignupPostDeliveryState,
)
from discordbot.schemas import SyncDiscordStateSchema
from events.models import Event
from events.tests._internal_client_orm import DiscordTestMixin
from org.models import Organization

BASE = "/api/internal/discord/signup-delivery/"
CHANNEL = "100000000000000001"
MESSAGE = "100000000000000002"
RECEIPT = {
    "parent_channel_id": CHANNEL,
    "message_id": MESSAGE,
    "thread_id": None,
    "kind": "text",
}


@override_settings(
    INTERNAL_SERVICE_TOKEN="synthetic-internal-key",
    INTERNAL_SERVICE_ALLOWED_IPS=["127.0.0.1"],
)
class InternalSignupDeliveryViewsTest(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.client.credentials(HTTP_X_INTERNAL_TOKEN="synthetic-internal-key")
        org = Organization.objects.create(name="Synthetic Organization")
        self.event = Event.objects.create(
            organization=org,
            name="Synthetic Event",
            scheduled_at=timezone.now() + timedelta(days=1),
        )

    def begin(self) -> dict:
        response = self.client.post(
            BASE + "begin/", {"event_id": self.event.pk}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def completion(self) -> dict:
        begin = self.begin()
        return {
            "event_id": self.event.pk,
            "generation": begin["generation"],
            "attempt_token": begin["attempt_token"],
            "outcome": "failed",
        }

    def test_begin_requires_internal_auth(self) -> None:
        self.client.credentials()
        for path, method in (
            ("begin/", "post"),
            ("sending/", "post"),
            ("complete/", "post"),
            ("blocked/", "get"),
        ):
            response = getattr(self.client, method)(BASE + path, {}, format="json")
            self.assertIn(response.status_code, (401, 403))
        self.assertFalse(SignupPostDeliveryState.objects.exists())

    def test_begin_complete_roundtrip_delivered(self) -> None:
        data = self.completion()
        log = DiscordMessageLog.objects.create(
            source="event_announcement",
            source_id=self.event.pk,
            channel_id=CHANNEL,
            embed_data={},
            success=None,
        )
        identity = {
            key: data[key] for key in ("event_id", "generation", "attempt_token")
        }
        response = self.client.post(
            BASE + "sending/", {**identity, "log_id": log.pk}, format="json"
        )
        self.assertEqual(response.json(), {"outcome": "ok"})
        data.update(outcome="delivered", receipt=RECEIPT, log_id=log.pk)
        response = self.client.post(BASE + "complete/", data, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["persisted"])
        self.assertEqual(response.json()["outcome"], "recorded")
        msg = DiscordEventMsgSignup.objects.get(event=self.event)
        self.assertEqual(msg.message_id, MESSAGE)
        self.assertTrue(msg.has_posted)
        response = self.client.post(BASE + "complete/", data, format="json")
        self.assertEqual(response.json()["outcome"], "idempotent")

    def test_complete_rejects_unsafe_failure_keys(self) -> None:
        data = self.completion()
        for failure in (
            {"message": "synthetic remote text"},
            {"phase": "create", "category": "http_error", "code": True},
            {"phase": "create", "category": "http_error", "status": "403"},
            {"phase": "remote text", "category": "http_error"},
            {"phase": "create", "category": "remote text"},
        ):
            with self.subTest(failure=failure):
                response = self.client.post(
                    BASE + "complete/", {**data, "failure": failure}, format="json"
                )
                self.assertEqual(response.status_code, 400)
                self.assertNotIn("synthetic remote text", response.content.decode())
        self.assertEqual(
            SignupPostDeliveryState.objects.get(event=self.event).state,
            SignupDeliveryStatus.RESERVED,
        )

    def test_complete_rejects_receipt_missing_message_id(self) -> None:
        data = self.completion()
        for receipt in (
            {key: value for key, value in RECEIPT.items() if key != "message_id"},
            {**RECEIPT, "message_id": True},
            {**RECEIPT, "message_id": "0"},
            {**RECEIPT, "thread_id": MESSAGE},
            {**RECEIPT, "kind": "forum"},
            {**RECEIPT, "message": "synthetic remote text"},
        ):
            with self.subTest(receipt=receipt):
                response = self.client.post(
                    BASE + "complete/",
                    {**data, "outcome": "delivered", "receipt": receipt},
                    format="json",
                )
                self.assertEqual(response.status_code, 400)

    def test_known_failure_sets_cooldown(self) -> None:
        data = self.completion()
        response = self.client.post(
            BASE + "complete/",
            {
                **data,
                "failure": {
                    "phase": "channel_lookup",
                    "category": "http_error",
                    "status": 403,
                    "code": 50013,
                },
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["persisted"])
        self.assertIsNotNone(response.json()["next_attempt_at"])
        self.assertEqual(self.begin()["outcome"], "deferred")

    def test_sync_state_includes_blocked_ids(self) -> None:
        self.begin()
        response = self.client.get("/api/internal/discord/sync-state/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["events_with_signup_blocked"], [self.event.pk])
        parsed = SyncDiscordStateSchema.model_validate(response.json())
        self.assertEqual(parsed.events_with_signup_blocked, [self.event.pk])

    def test_clear_with_expected_message_id_scopes_reset(self) -> None:
        msg = DiscordEventMsgSignup.objects.create(
            event=self.event, channel_id=CHANNEL, message_id=MESSAGE, has_posted=True
        )
        url = "/api/internal/discord/signup-message/clear/"
        for expected, cleared in (("100000000000000003", False), (MESSAGE, True)):
            response = self.client.post(
                url,
                {"event_id": self.event.pk, "expected_message_id": expected},
                format="json",
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["cleared"], cleared)
        msg.refresh_from_db()
        self.assertFalse(msg.has_posted)

    def test_blocked_endpoint(self) -> None:
        self.begin()
        response = self.client.get(
            BASE + "blocked/", {"event_ids": f"{self.event.pk},999999"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"event_ids": [self.event.pk]})
        for event_ids in ("x", "1,,2", "-1", "true"):
            response = self.client.get(BASE + "blocked/", {"event_ids": event_ids})
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get(BASE + "blocked/").json(), {"event_ids": []})

    def test_missing_event_returns_not_found(self) -> None:
        response = self.client.post(
            BASE + "begin/", {"event_id": 999999}, format="json"
        )
        self.assertEqual(response.status_code, 404)

    def test_invalid_identity_rejected_without_mutation(self) -> None:
        for data in ({"event_id": True}, {"event_id": self.event.pk, "generation": -1}):
            response = self.client.post(BASE + "begin/", data, format="json")
            self.assertEqual(response.status_code, 400)
        self.assertFalse(SignupPostDeliveryState.objects.exists())


class SignupDeliveryClientTest(TestCase):
    def test_clients_fail_closed_on_unavailable_or_malformed_response(self) -> None:
        for status, body in (
            (500, b"{}"),
            (200, b"[]"),
            (200, b"not json"),
            (200, b"{}"),
        ):
            response = requests.Response()
            response.status_code = status
            response._content = body
            with (
                self.subTest(status=status, body=body),
                patch("app.internal_client.transport.post", return_value=response),
                patch("app.internal_client.transport.get", return_value=response),
            ):
                self.assertIsNone(internal_client.begin_signup_delivery(1, None))
                self.assertFalse(
                    internal_client.mark_signup_delivery_sending(1, 0, "synthetic", 1)
                )
                self.assertIsNone(
                    internal_client.complete_signup_delivery(
                        1, 0, "synthetic", "failed"
                    )
                )
                self.assertIsNone(internal_client.get_signup_blocked_event_ids([1]))

    def test_blocked_reply_and_clear_identity(self) -> None:
        response = requests.Response()
        response.status_code = 200
        response._content = b'{"event_ids": [1, 2]}'
        with patch("app.internal_client.transport.get", return_value=response):
            self.assertEqual(
                internal_client.get_signup_blocked_event_ids([1, 2]), {1, 2}
            )
        with patch("app.internal_client.transport.post", return_value=response) as post:
            internal_client.clear_event_signup_state(1, expected_message_id=MESSAGE)
            self.assertEqual(
                post.call_args.args[1], {"event_id": 1, "expected_message_id": MESSAGE}
            )


class SignupDeliveryOrmFakeTest(DiscordTestMixin, TestCase):
    def setUp(self) -> None:
        super().setUp()
        org = Organization.objects.create(name="Synthetic Organization")
        self.event = Event.objects.create(
            organization=org,
            name="Synthetic Event",
            scheduled_at=timezone.now() + timedelta(days=1),
        )

    def test_fakes_roundtrip_through_internal_views(self) -> None:
        begin = internal_client.begin_signup_delivery(self.event.pk, None)
        self.assertEqual(begin.outcome, "reserved")
        self.assertEqual(
            internal_client.get_signup_blocked_event_ids([self.event.pk]),
            {self.event.pk},
        )
        log = DiscordMessageLog.objects.create(
            source="event_announcement",
            source_id=self.event.pk,
            channel_id=CHANNEL,
            embed_data={},
            success=None,
        )
        self.assertTrue(
            internal_client.mark_signup_delivery_sending(
                self.event.pk, begin.generation, begin.attempt_token, log.pk
            )
        )
        reply = internal_client.complete_signup_delivery(
            self.event.pk,
            begin.generation,
            begin.attempt_token,
            "delivered",
            receipt=RECEIPT,
            log_id=log.pk,
        )
        self.assertEqual((reply.outcome, reply.persisted), ("recorded", True))
        self.assertIsNone(
            internal_client.complete_signup_delivery(
                self.event.pk,
                begin.generation,
                begin.attempt_token,
                "failed",
                failure={"message": "x"},
            )
        )
        stale = internal_client.clear_event_signup_state(
            self.event.pk, expected_message_id="100000000000000003"
        )
        self.assertFalse(stale.json()["cleared"])
        current = internal_client.clear_event_signup_state(
            self.event.pk, expected_message_id=MESSAGE
        )
        self.assertTrue(current.json()["cleared"])
        self.assertFalse(DiscordEventMsgSignup.objects.get(event=self.event).has_posted)


@override_settings(
    INTERNAL_SERVICE_TOKEN="synthetic-internal-key",
    INTERNAL_SERVICE_ALLOWED_IPS=["127.0.0.1"],
)
class SignupDeliveryValidationTest(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.client.credentials(HTTP_X_INTERNAL_TOKEN="synthetic-internal-key")
        org = Organization.objects.create(name="Synthetic Organization")
        self.event = Event.objects.create(
            organization=org,
            name="Synthetic Event",
            scheduled_at=timezone.now() + timedelta(days=1),
        )

    def test_request_ids_must_fit_database_range(self) -> None:
        response = self.client.post(BASE + "begin/", {"event_id": 2**63}, format="json")
        self.assertEqual(response.status_code, 400)
        response = self.client.get(BASE + "blocked/", {"event_ids": str(2**63)})
        self.assertEqual(response.status_code, 400)

    def test_blocked_endpoint_accepts_more_than_500_ids(self) -> None:
        ids = list(range(1, 502))
        response = self.client.get(
            BASE + "blocked/", {"event_ids": ",".join(map(str, ids))}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"event_ids": []})

    def test_client_rejects_invalid_reservation_identity(self) -> None:
        for body in (
            b'{"outcome":"reserved","generation":0,"attempt_token":"invalid","attempt":1}',
            b'{"outcome":"in_flight","generation":0,"attempt_token":"invalid"}',
            b'{"outcome":"in_flight","generation":0,"attempt":1}',
        ):
            response = requests.Response()
            response.status_code = 200
            response._content = body
            with (
                self.subTest(body=body),
                patch("app.internal_client.transport.post", return_value=response),
            ):
                self.assertIsNone(
                    internal_client.begin_signup_delivery(self.event.pk, None)
                )

    def test_clear_rejects_null_expected_identity(self) -> None:
        msg = DiscordEventMsgSignup.objects.create(
            event=self.event,
            channel_id=CHANNEL,
            message_id=MESSAGE,
            has_posted=True,
        )
        response = self.client.post(
            "/api/internal/discord/signup-message/clear/",
            {"event_id": self.event.pk, "expected_message_id": None},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        msg.refresh_from_db()
        self.assertTrue(msg.has_posted)
