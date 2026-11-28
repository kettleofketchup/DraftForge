import csv
import io
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest import mock
from uuid import uuid4

from django.core.cache.backends.locmem import LocMemCache
from django.test import override_settings
from django.urls import reverse
from rest_framework.response import Response
from rest_framework.test import APIClient
from structlog.testing import capture_logs

from app.models import CustomUser
from events.constants import ActorRole, EventState, SignupMeans, SignupStatus
from events.ledger import RecordsWindow, event_snapshot, user_snapshot
from events.models import Event, EventRepeater, SignupLedgerEntry
from events.records import (
    RECORD_COLUMNS,
    RecordsFilter,
    build_signup_records,
    flatten_record,
    guard_csv_cell,
)
from events.tests.base import EventTestCase
from events.views_records import SignupRecordsThrottle
from league.models import League
from org.api_tokens.tokens import issue_token
from org.models import Organization

TOKEN = "test-internal-token"
T0 = datetime(2026, 3, 1, 18, 0, tzinfo=UTC)
ALL = RecordsFilter(window=RecordsWindow())
VIEWED_KEYS = {
    "org_id",
    "format",
    "row_count",
    "has_since",
    "has_until",
    "filter_series",
    "filter_event",
    "filter_user",
    "via",
}
LOG_META_KEYS = {"event", "log_level", "system", "subsystem"}


def _after(status: str = SignupStatus.CONFIRMED) -> dict[str, Any]:
    return {
        "status": status,
        "commitment": "main",
        "rsvp_class": "standard",
        "signed_up_at": (T0 - timedelta(days=2)).isoformat(),
        "line_seq": 1,
        "waitlist_position": None,
        "event_team_id": None,
        "extra": {},
    }


@override_settings(INTERNAL_SERVICE_TOKEN=TOKEN)
class SignupRecordsApiTest(EventTestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.member = CustomUser.objects.create_user(
            username="records_member", password="x"
        )
        cls.org_staff = CustomUser.objects.create_user(
            username="records_staff", password="x"
        )
        cls.org.staff.add(cls.org_staff)
        cls.org_admin = CustomUser.objects.create_user(
            username="records_org_admin", password="x"
        )
        cls.org.admins.add(cls.org_admin)
        cls.site_admin = CustomUser.objects.create_user(
            username="records_site_admin", password="x", is_staff=True
        )
        cls.other_org_staff = CustomUser.objects.create_user(
            username="records_other_staff", password="x"
        )
        cls.other_org = Organization.objects.create(
            name="Records Other Org", owner=cls.other_org_staff
        )
        cls.other_org.staff.add(cls.other_org_staff)
        cls.in_org_league_staff = CustomUser.objects.create_user(
            username="records_league_staff", password="x"
        )
        league = League.objects.create(
            name="Records League", organization=cls.org, steam_league_id=77777
        )
        league.staff.add(cls.in_org_league_staff)

    def setUp(self) -> None:
        self.throttle_cache = LocMemCache(f"signup-records-{uuid4().hex}", {})
        patcher = mock.patch.object(SignupRecordsThrottle, "cache", self.throttle_cache)
        patcher.start()
        self.addCleanup(patcher.stop)

    # Helpers

    def _url(self, org: Organization | int | None = None) -> str:
        pk = org if isinstance(org, int) else (org or self.org).pk
        return reverse("org-signup-records", args=[pk])

    def _get(
        self,
        user: CustomUser | None,
        params: dict[str, Any] | None = None,
        org: Organization | int | None = None,
        **headers: str,
    ) -> Response:
        client = APIClient()
        if user is not None:
            client.force_login(user)
        return client.get(self._url(org), params or {}, **headers)

    def _internal(
        self, params: dict[str, Any] | None = None, **headers: str
    ) -> Response:
        headers.setdefault("HTTP_X_INTERNAL_TOKEN", TOKEN)
        return APIClient().get(
            reverse("internal_signup_records"), params or {}, **headers
        )

    def _row(
        self,
        event: Event,
        user: CustomUser | None,
        at: datetime,
        *,
        after: dict[str, Any] | None = None,
        subject_snapshot: dict[str, Any] | None = None,
        snapshot: dict[str, Any] | None = None,
    ) -> SignupLedgerEntry:
        return SignupLedgerEntry.objects.create(
            event_id=event.pk,
            organization=self.org,
            event_snapshot=snapshot if snapshot is not None else event_snapshot(event),
            subject_user=user,
            subject_snapshot=(
                subject_snapshot
                if subject_snapshot is not None
                else user_snapshot(user) or {}
            ),
            actor_user=self.admin,
            actor_snapshot=user_snapshot(self.admin),
            actor_role=ActorRole.STAFF,
            means=SignupMeans.DISCORD_BUTTON,
            action="signed_up",
            after=after if after is not None else _after(),
            correlation_id=uuid.uuid4().hex,
            occurred_at=at,
        )

    def _signed(self, event: Event, user: CustomUser | None = None) -> None:
        self._row(event, user or self.user, T0 - timedelta(days=1))

    def _event_ids(self, response: Response) -> list[int]:
        return [r["event_id"] for r in response.json()["results"]]

    def _assert_json_error(self, response: Response, status: int) -> Any:
        self.assertEqual(response.status_code, status, response.content)
        self.assertTrue(
            response["Content-Type"].startswith("application/json"),
            response["Content-Type"],
        )
        return json.loads(response.content)

    def _csv(self, response: Response) -> list[list[str]]:
        return list(csv.reader(io.StringIO(response.content.decode("utf-8"))))

    def _viewed(self, logs: list[dict[str, Any]]) -> dict[str, Any]:
        viewed = [e for e in logs if e["event"] == "signup_records_viewed"]
        self.assertEqual(len(viewed), 1)
        return viewed[0]

    # Authorization

    def test_permission_matrix(self) -> None:
        self._signed(self.make_event(scheduled_at=T0))
        self.assertIn(self._get(None).status_code, (401, 403))
        with capture_logs() as logs:
            self.assertEqual(self._get(self.member).status_code, 403)
        denied = [e for e in logs if e["event"] == "signup_records_denied"]
        self.assertEqual(len(denied), 1)
        self.assertEqual(denied[0]["org_id"], self.org.pk)
        self.assertEqual(denied[0]["user_id"], self.member.pk)
        self.assertEqual(denied[0]["endpoint"], "records")
        self.assertEqual(denied[0]["system"], "events")
        self.assertEqual(denied[0]["subsystem"], "ledger")
        self.assertEqual(self._get(self.other_org_staff).status_code, 403)
        self.assertEqual(self._get(self.in_org_league_staff).status_code, 403)
        for user in (self.org_staff, self.org_admin, self.site_admin):
            response = self._get(user)
            self.assertEqual(response.status_code, 200, user.username)
            self.assertEqual(response.json()["count"], 1)
        self.assertEqual(self._get(self.org_staff, org=999999).status_code, 404)

    def test_org_endpoint_rejects_tokens(self) -> None:
        issued = issue_token(self.org, self.org_staff, "records")
        bearer = APIClient()
        bearer.credentials(HTTP_AUTHORIZATION=f"Bearer {issued.raw}")
        self.assertIn(bearer.get(self._url()).status_code, (401, 403))
        internal = APIClient().get(self._url(), HTTP_X_INTERNAL_TOKEN=TOKEN)
        self.assertIn(internal.status_code, (401, 403))

    def test_internal_auth(self) -> None:
        self._signed(self.make_event(scheduled_at=T0))
        url = reverse("internal_signup_records")
        params = {"organization": self.org.pk}
        self.assertIn(APIClient().get(url, params).status_code, (401, 403))
        self.assertIn(
            self._internal(params, HTTP_X_INTERNAL_TOKEN="wrong").status_code,
            (401, 403),
        )
        session = APIClient()
        session.force_login(self.site_admin)
        self.assertEqual(session.get(url, params).status_code, 403)

        missing = self._assert_json_error(self._internal(), 400)
        self.assertIn("organization", missing)
        self.assertIn(
            "organization",
            self._assert_json_error(self._internal({"organization": "abc"}), 400),
        )
        self.assertEqual(self._internal({"organization": 999999}).status_code, 404)

        internal = self._internal(params)
        self.assertEqual(internal.status_code, 200, internal.content)
        self.assertEqual(internal.json(), self._get(self.org_staff).json())

    # Content

    def test_deleted_and_cancelled_events_present(self) -> None:
        cancelled = self.make_event(scheduled_at=T0, state=EventState.CANCELLED)
        gone = self.make_event(scheduled_at=T0 + timedelta(days=1), name="Gone")
        self._signed(cancelled)
        self._signed(gone)
        gone_pk = gone.pk
        Event.objects.filter(pk=gone_pk).delete()

        results = self._get(self.org_staff).json()["results"]

        states = {r["event_id"]: r["event_state"] for r in results}
        self.assertEqual(
            states, {cancelled.pk: EventState.CANCELLED, gone_pk: "deleted"}
        )

    def test_filters_and_400s(self) -> None:
        repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Weekly",
            frequency="weekly",
            day_of_week=1,
            time_of_day="20:00",
            starts_at="2026-01-01",
        )
        early = self.make_event(scheduled_at=T0 - timedelta(days=10))
        mid = self.make_event(scheduled_at=T0, event_repeater=repeater)
        late = self.make_event(scheduled_at=T0 + timedelta(days=10))
        for event in (early, mid, late):
            self._signed(event)
        self._signed(late, self.admin)

        def ids(params: dict[str, Any]) -> list[int]:
            response = self._get(self.org_staff, params)
            self.assertEqual(response.status_code, 200, response.content)
            return self._event_ids(response)

        self.assertEqual(
            ids({"since": "2026-02-25T00:00:00Z"}), [mid.pk, late.pk, late.pk]
        )
        self.assertEqual(
            ids({"until": "2026-03-05T00:00:00+00:00"}), [early.pk, mid.pk]
        )
        self.assertEqual(ids({"series": repeater.pk}), [mid.pk])
        self.assertEqual(ids({"event": early.pk}), [early.pk])
        self.assertEqual(ids({"user": self.admin.pk}), [late.pk])

        bad = self._assert_json_error(self._get(self.org_staff, {"since": "bad"}), 400)
        self.assertIsInstance(bad["since"], list)
        naive = self._get(self.org_staff, {"until": "2026-03-01T10:00:00"})
        self.assertIn("until", self._assert_json_error(naive, 400))
        reversed_range = self._get(
            self.org_staff, {"since": "2026-03-05", "until": "2026-03-01"}
        )
        self.assertIn("until", self._assert_json_error(reversed_range, 400))
        self.assertIn(
            "series",
            self._assert_json_error(self._get(self.org_staff, {"series": "x"}), 400),
        )

    def test_org_timezone_dates(self) -> None:
        Organization.objects.filter(pk=self.org.pk).update(timezone="America/New_York")
        inside = self.make_event(scheduled_at=datetime(2026, 3, 13, 1, 0, tzinfo=UTC))
        outside = self.make_event(scheduled_at=datetime(2026, 3, 10, 1, 0, tzinfo=UTC))
        self._signed(inside)
        self._signed(outside)
        params = {"since": "2026-03-10", "until": "2026-03-13"}

        self.assertEqual(
            self._event_ids(self._get(self.org_staff, params)), [inside.pk]
        )
        internal = self._internal({**params, "organization": self.org.pk})
        self.assertEqual(self._event_ids(internal), [inside.pk])

    def test_moved_event(self) -> None:
        event = self.make_event(scheduled_at=T0, name="Original Name")
        self._signed(event)
        Event.objects.filter(pk=event.pk).update(
            organization=self.other_org, name="New Org Name"
        )

        (record,) = self._get(self.org_staff).json()["results"]

        self.assertEqual(record["event_state"], "moved")
        self.assertEqual(record["event_name"], "Original Name")

    # CSV

    def test_csv_format(self) -> None:
        self._signed(self.make_event(scheduled_at=T0))
        for response in (
            self._get(self.org_staff, {"format": "csv"}),
            self._get(self.org_staff, HTTP_ACCEPT="text/csv"),
        ):
            self.assertEqual(response.status_code, 200, response.content)
            self.assertTrue(response["Content-Type"].startswith("text/csv"))
            disposition = response["Content-Disposition"]
            self.assertTrue(disposition.startswith("attachment; filename="))
            self.assertRegex(
                disposition,
                rf'filename="signup-records-{self.org.pk}-\d{{8}}\.csv"$',
            )
            rows = self._csv(response)
            self.assertEqual(rows[0], list(RECORD_COLUMNS))
            self.assertEqual(len(rows), 2)

    def test_csv_json_parity(self) -> None:
        dash = self.make_event(scheduled_at=T0, name="-Weekly Inhouse-")
        formula = self.make_event(
            scheduled_at=T0 + timedelta(days=1), name='=HYPERLINK("x")'
        )
        self._signed(dash)
        self._signed(formula)
        gone = CustomUser.objects.create_user(username="records_gone", password="x")
        self._row(
            dash,
            gone,
            T0 - timedelta(days=1),
            subject_snapshot={
                "user_id": gone.pk,
                "username": "records_gone",
                "nickname": None,
                "discord_id": "=1+1",
            },
        )
        gone.delete()

        records = build_signup_records(self.org.pk, ALL)
        csv_rows = self._csv(self._get(self.org_staff, {"format": "csv"}))
        json_rows = self._get(self.org_staff).json()["results"]

        self.assertEqual(len(records), 3)
        self.assertEqual(
            csv_rows[1:],
            [
                [
                    str(guard_csv_cell(v)) if v is not None else ""
                    for v in flatten_record(r)
                ]
                for r in records
            ],
        )
        flat = [cell for row in csv_rows[1:] for cell in row]
        self.assertIn("'-Weekly Inhouse-", flat)
        self.assertIn('\'=HYPERLINK("x")', flat)
        self.assertIn("'=1+1", flat)
        self.assertEqual(
            {r["event_name"] for r in json_rows},
            {"-Weekly Inhouse-", '=HYPERLINK("x")'},
        )
        self.assertIn("=1+1", {r["discord_id"] for r in json_rows})

    def test_no_actor_discord_id(self) -> None:
        self._signed(self.make_event(scheduled_at=T0))

        json_response = self._get(self.org_staff)
        csv_response = self._get(self.org_staff, {"format": "csv"})

        for row in json_response.json()["results"]:
            self.assertFalse([k for k in row if k.startswith("actor")])
        self.assertNotIn(b"actor", json_response.content)
        self.assertNotIn(self.admin.discordId.encode(), json_response.content)
        header = self._csv(csv_response)[0]
        self.assertFalse([c for c in header if "actor" in c])
        self.assertNotIn(self.admin.discordId.encode(), csv_response.content)

    @override_settings(SIGNUP_RECORDS_MAX_ROWS=1)
    def test_too_many_records(self) -> None:
        self._signed(self.make_event(scheduled_at=T0))
        self._signed(self.make_event(scheduled_at=T0 + timedelta(days=1)))
        expected = {
            "detail": "Too many records; narrow the date range.",
            "code": "too_many_records",
        }
        for params in ({}, {"format": "csv"}):
            body = self._assert_json_error(self._get(self.org_staff, params), 400)
            self.assertEqual(body, expected)
        internal = self._internal({"organization": self.org.pk})
        self.assertEqual(self._assert_json_error(internal, 400), expected)

    def test_csv_errors_render_json(self) -> None:
        csv_params = {"format": "csv"}
        self._assert_json_error(
            self._get(self.org_staff, {**csv_params, "since": "bad"}), 400
        )
        with override_settings(SIGNUP_RECORDS_MAX_ROWS=0):
            self._signed(self.make_event(scheduled_at=T0))
            body = self._assert_json_error(self._get(self.org_staff, csv_params), 400)
            self.assertEqual(body["code"], "too_many_records")
        anon = self._get(None, csv_params)
        self._assert_json_error(anon, anon.status_code)
        self.assertIn(anon.status_code, (401, 403))
        self._assert_json_error(self._get(self.member, csv_params), 403)
        self._assert_json_error(self._get(self.member, HTTP_ACCEPT="text/csv"), 403)
        self._assert_json_error(self._get(self.org_staff, csv_params, org=999999), 404)
        self._assert_json_error(
            self._internal({**csv_params, "organization": "abc"}), 400
        )
        for _ in range(10):
            self._get(self.org_admin, csv_params)
        self._assert_json_error(self._get(self.org_admin, csv_params), 429)

    def test_empty_range(self) -> None:
        self.assertEqual(
            self._get(self.org_staff).json(),
            {"organization": self.org.pk, "count": 0, "results": []},
        )
        self.make_event(scheduled_at=T0)
        response = self._get(self.org_staff, {"format": "csv", "since": "2030-01-01"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.content.decode("utf-8").splitlines(), [",".join(RECORD_COLUMNS)]
        )

    def test_viewed_log(self) -> None:
        event = self.make_event(scheduled_at=T0)
        self._signed(event)
        with capture_logs() as logs:
            self._get(
                self.org_staff,
                {"since": "2026-01-01", "event": event.pk, "format": "csv"},
            )
        viewed = self._viewed(logs)
        self.assertEqual(set(viewed) - LOG_META_KEYS, VIEWED_KEYS)
        self.assertEqual(viewed["system"], "events")
        self.assertEqual(viewed["subsystem"], "ledger")
        self.assertEqual(viewed["org_id"], self.org.pk)
        self.assertEqual(viewed["format"], "csv")
        self.assertEqual(viewed["row_count"], 1)
        self.assertTrue(viewed["has_since"])
        self.assertFalse(viewed["has_until"])
        self.assertFalse(viewed["filter_series"])
        self.assertTrue(viewed["filter_event"])
        self.assertFalse(viewed["filter_user"])
        self.assertEqual(viewed["via"], "org")

        with capture_logs() as logs:
            self._internal({"organization": self.org.pk})
        internal = self._viewed(logs)
        self.assertEqual(internal["via"], "internal")
        self.assertEqual(internal["format"], "json")

    def test_throttle(self) -> None:
        for _ in range(10):
            self.assertEqual(self._get(self.org_staff).status_code, 200)
        self.assertEqual(self._get(self.org_staff).status_code, 429)
        self.assertEqual(self._internal({"organization": self.org.pk}).status_code, 200)
