import uuid
from base64 import urlsafe_b64encode
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest import mock
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from django.core.cache.backends.locmem import LocMemCache
from django.test import override_settings
from django.urls import reverse
from rest_framework.response import Response
from rest_framework.test import APIClient
from structlog.testing import capture_logs

from app.models import CustomUser
from events.constants import ActorRole, SignupAction, SignupMeans, SignupStatus
from events.history import MAX_DB_INT, LedgerCursor, decode_ledger_cursor
from events.ledger import event_snapshot, user_snapshot
from events.models import Event, SignupLedgerEntry
from events.serializers import SignupLedgerEntrySerializer
from events.tests.base import EventTestCase
from events.views_records import SignupRecordsThrottle
from league.models import League
from org.api_tokens.tokens import issue_token
from org.models import Organization

TOKEN = "test-internal-token"
T0 = datetime(2026, 3, 1, 18, 0, tzinfo=UTC)
ENVELOPE_KEYS = {"count", "next", "previous", "results"}


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


class LedgerCursorTest(EventTestCase):
    def test_cursor_roundtrip(self) -> None:
        for pk in (1, 42, MAX_DB_INT):
            cursor = LedgerCursor(pk)
            self.assertEqual(decode_ledger_cursor(cursor.token), cursor)

    def test_cursor_invalid(self) -> None:
        def token(raw: str) -> str:
            return urlsafe_b64encode(raw.encode()).decode().rstrip("=")

        for bad in ("", "!!", token("0"), token(str(MAX_DB_INT + 1)), token("x")):
            with (
                self.subTest(bad=bad),
                self.assertRaisesMessage(ValueError, "Invalid cursor."),
            ):
                decode_ledger_cursor(bad)


@override_settings(INTERNAL_SERVICE_TOKEN=TOKEN)
class SignupLedgerApiTest(EventTestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.member = CustomUser.objects.create_user(
            username="ledger_member", password="x"
        )
        cls.org_staff = CustomUser.objects.create_user(
            username="ledger_staff", password="x"
        )
        cls.org.staff.add(cls.org_staff)
        cls.other_org_staff = CustomUser.objects.create_user(
            username="ledger_other_staff", password="x"
        )
        cls.other_org = Organization.objects.create(
            name="Ledger Other Org", owner=cls.other_org_staff
        )
        cls.other_org.staff.add(cls.other_org_staff)
        cls.in_org_league_staff = CustomUser.objects.create_user(
            username="ledger_league_staff", password="x"
        )
        league = League.objects.create(
            name="Ledger League", organization=cls.org, steam_league_id=77778
        )
        league.staff.add(cls.in_org_league_staff)

    def setUp(self) -> None:
        cache = LocMemCache(f"signup-ledger-{uuid4().hex}", {})
        patcher = mock.patch.object(SignupRecordsThrottle, "cache", cache)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _get(
        self,
        user: CustomUser | None,
        params: dict[str, Any] | None = None,
        org: Organization | int | None = None,
        **headers: str,
    ) -> Response:
        pk = org if isinstance(org, int) else (org or self.org).pk
        client = APIClient()
        if user is not None:
            client.force_login(user)
        return client.get(
            reverse("org-signup-ledger", args=[pk]), params or {}, **headers
        )

    def _internal(
        self, params: dict[str, Any] | None = None, **headers: str
    ) -> Response:
        headers.setdefault("HTTP_X_INTERNAL_TOKEN", TOKEN)
        return APIClient().get(
            reverse("internal_signup_ledger"), params or {}, **headers
        )

    def _row(
        self,
        event: Event,
        user: CustomUser | None,
        at: datetime,
        *,
        org: Organization | None = None,
        subject_snapshot: dict[str, Any] | None = None,
        action: str = SignupAction.SIGNED_UP,
        after: dict[str, Any] | None = None,
    ) -> SignupLedgerEntry:
        return SignupLedgerEntry.objects.create(
            event_id=event.pk,
            organization=org or self.org,
            event_snapshot=event_snapshot(event),
            subject_user=user,
            subject_snapshot=(
                subject_snapshot
                if subject_snapshot is not None
                else user_snapshot(user) or {}
            ),
            actor_user=self.admin,
            actor_snapshot=user_snapshot(self.admin),
            actor_role=ActorRole.STAFF,
            means=SignupMeans.WEB,
            action=action,
            after=after if after is not None else _after(),
            correlation_id=uuid.uuid4().hex,
            occurred_at=at,
        )

    def _ids(self, response: Response) -> list[int]:
        self.assertEqual(response.status_code, 200, response.content)
        return [r["id"] for r in response.json()["results"]]

    def _cursor(self, response: Response) -> str:
        next_url = response.json()["next"]
        self.assertIsNotNone(next_url)
        return parse_qs(urlparse(next_url).query)["cursor"][0]

    # Pagination

    def test_pagination_ascending_pk(self) -> None:
        event = self.make_event(scheduled_at=T0)
        rows = [self._row(event, self.user, T0 - timedelta(hours=i)) for i in range(5)]
        pks = [r.pk for r in rows]

        first = self._get(self.org_staff, {"page_size": 2})
        self.assertEqual(set(first.json()), ENVELOPE_KEYS)
        self.assertEqual(first.json()["count"], 5)
        self.assertIsNone(first.json()["previous"])
        self.assertEqual(self._ids(first), pks[:2])
        second = self._get(
            self.org_staff, {"page_size": 2, "cursor": self._cursor(first)}
        )
        self.assertEqual(self._ids(second), pks[2:4])
        last = self._get(
            self.org_staff, {"page_size": 2, "cursor": self._cursor(second)}
        )
        self.assertEqual(self._ids(last), pks[4:])
        self.assertIsNone(last.json()["next"])

    def test_default_page_size(self) -> None:
        event = self.make_event(scheduled_at=T0)
        for i in range(51):
            self._row(event, self.user, T0 + timedelta(minutes=i))
        response = self._get(self.org_staff)
        self.assertEqual(len(self._ids(response)), 50)
        self.assertIsNotNone(response.json()["next"])
        self.assertEqual(
            len(self._ids(self._get(self.org_staff, {"page_size": 100}))), 51
        )

    def test_late_row_with_earlier_occurred_at_not_skipped(self) -> None:
        event = self.make_event(scheduled_at=T0)
        for i in range(3):
            self._row(event, self.user, T0 + timedelta(hours=i))
        first = self._get(self.org_staff, {"page_size": 2})
        cursor = self._cursor(first)
        late = self._row(event, self.admin, T0 - timedelta(days=30))

        rest = self._get(self.org_staff, {"page_size": 2, "cursor": cursor})

        self.assertIn(late.pk, self._ids(rest))

    def test_invalid_cursor_400(self) -> None:
        response = self._get(self.org_staff, {"cursor": "!!"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"cursor": ["Invalid cursor."]})
        for size in ("0", "101", "x"):
            bad = self._get(self.org_staff, {"page_size": size})
            self.assertEqual(bad.status_code, 400, size)
            self.assertIn("page_size", bad.json())

    # Rows

    def test_ready_check_rows_included(self) -> None:
        event = self.make_event(scheduled_at=T0)
        row = self._row(
            event,
            None,
            T0,
            subject_snapshot={},
            action=SignupAction.READY_CHECK_TRANSITION,
            after=None,
        )

        (entry,) = self._get(self.org_staff).json()["results"]

        self.assertEqual(entry["id"], row.pk)
        self.assertIsNone(entry["subject"])

    def test_history_serializer_keeps_ready_check_subject(self) -> None:
        event = self.make_event(scheduled_at=T0)
        row = self._row(
            event,
            None,
            T0,
            subject_snapshot={},
            action=SignupAction.READY_CHECK_TRANSITION,
            after=None,
        )

        subject = SignupLedgerEntrySerializer(row).data["subject"]

        self.assertIsInstance(subject, dict)
        self.assertTrue(all(v is None for v in subject.values()))

    def test_deleted_event_block(self) -> None:
        live = self.make_event(scheduled_at=T0, name="Live Night")
        gone = self.make_event(scheduled_at=T0 + timedelta(days=1), name="Gone Night")
        self._row(live, self.user, T0)
        self._row(gone, self.user, T0)
        gone_pk = gone.pk
        Event.objects.filter(pk=gone_pk).delete()

        results = self._get(self.org_staff).json()["results"]

        by_event = {r["event_id"]: r for r in results}
        self.assertEqual(
            by_event[gone_pk]["event"],
            {
                "name": "Gone Night",
                "state": "deleted",
                "scheduled_at": "2026-03-02T18:00:00Z",
            },
        )
        self.assertEqual(by_event[live.pk]["event"]["name"], "Live Night")
        self.assertEqual(by_event[live.pk]["event"]["state"], live.state)
        for row in results:
            self.assertEqual(row["organization_id"], self.org.pk)

    def test_actor_has_no_discord_id(self) -> None:
        CustomUser.objects.filter(pk=self.admin.pk).update(
            discordId="190000000000000009"
        )
        CustomUser.objects.filter(pk=self.user.pk).update(
            discordId="190000000000000001"
        )
        self._row(self.make_event(scheduled_at=T0), self.user, T0)

        (row,) = self._get(self.org_staff).json()["results"]

        self.assertNotIn("discord_id", row["actor"])
        self.assertNotIn("actor_snapshot", row)
        self.assertEqual(row["subject"]["discord_id"], "190000000000000001")

    def test_filters(self) -> None:
        early = self.make_event(scheduled_at=T0 - timedelta(days=10))
        late = self.make_event(scheduled_at=T0 + timedelta(days=10))
        a = self._row(early, self.user, T0)
        b = self._row(late, self.user, T0)
        c = self._row(late, self.admin, T0)

        self.assertEqual(
            self._ids(self._get(self.org_staff, {"since": "2026-03-05"})), [b.pk, c.pk]
        )
        self.assertEqual(
            self._ids(self._get(self.org_staff, {"until": "2026-03-05"})), [a.pk]
        )
        self.assertEqual(
            self._ids(self._get(self.org_staff, {"event": early.pk})), [a.pk]
        )
        self.assertEqual(
            self._ids(self._get(self.org_staff, {"user": self.admin.pk})), [c.pk]
        )
        filtered = self._get(self.org_staff, {"since": "2026-03-05", "page_size": 1})
        self.assertEqual(filtered.json()["count"], 2)
        self.assertEqual(self._get(self.org_staff, {"since": "bad"}).status_code, 400)

    def test_other_org_rows_excluded(self) -> None:
        mine = self._row(self.make_event(scheduled_at=T0), self.user, T0)
        theirs = Event.objects.create(
            organization=self.other_org, name="Theirs", scheduled_at=T0
        )
        self._row(theirs, self.user, T0, org=self.other_org)

        self.assertEqual(self._ids(self._get(self.org_staff)), [mine.pk])

    # Authorization

    def test_permissions_and_tokens(self) -> None:
        self._row(self.make_event(scheduled_at=T0), self.user, T0)
        self.assertIn(self._get(None).status_code, (401, 403))
        with capture_logs() as logs:
            self.assertEqual(self._get(self.member).status_code, 403)
        (denied,) = [e for e in logs if e["event"] == "signup_records_denied"]
        self.assertEqual(denied["endpoint"], "ledger")
        self.assertEqual(denied["user_id"], self.member.pk)
        self.assertEqual(self._get(self.other_org_staff).status_code, 403)
        self.assertEqual(self._get(self.in_org_league_staff).status_code, 403)
        self.assertEqual(self._get(self.org_staff).status_code, 200)
        self.assertEqual(self._get(self.org_staff, org=999999).status_code, 404)

        issued = issue_token(self.org, self.org_staff, "ledger")
        bearer = APIClient()
        bearer.credentials(HTTP_AUTHORIZATION=f"Bearer {issued.raw}")
        url = reverse("org-signup-ledger", args=[self.org.pk])
        self.assertIn(bearer.get(url).status_code, (401, 403))
        self.assertIn(
            APIClient().get(url, HTTP_X_INTERNAL_TOKEN=TOKEN).status_code, (401, 403)
        )

        internal_url = reverse("internal_signup_ledger")
        params = {"organization": self.org.pk}
        self.assertIn(APIClient().get(internal_url, params).status_code, (401, 403))
        self.assertIn(
            self._internal(params, HTTP_X_INTERNAL_TOKEN="wrong").status_code,
            (401, 403),
        )
        self.assertEqual(self._internal().status_code, 400)
        self.assertEqual(self._internal({"organization": "abc"}).status_code, 400)
        self.assertEqual(self._internal({"organization": 999999}).status_code, 404)
        internal = self._internal(params)
        self.assertEqual(internal.status_code, 200, internal.content)
        self.assertEqual(
            internal.json()["results"], self._get(self.org_staff).json()["results"]
        )

    def test_viewed_log(self) -> None:
        self._row(self.make_event(scheduled_at=T0), self.user, T0)
        with capture_logs() as logs:
            self._get(
                self.org_staff,
                {"since": "2026-02-01", "user": self.user.pk, "page_size": 10},
            )
        (viewed,) = [e for e in logs if e["event"] == "signup_ledger_viewed"]
        self.assertEqual(viewed["system"], "events")
        self.assertEqual(viewed["subsystem"], "ledger")
        self.assertEqual(viewed["org_id"], self.org.pk)
        self.assertEqual(viewed["page_size"], 10)
        self.assertFalse(viewed["has_cursor"])
        self.assertTrue(viewed["has_since"])
        self.assertFalse(viewed["has_until"])
        self.assertTrue(viewed["filter_user"])
        self.assertFalse(viewed["filter_event"])
        self.assertFalse(viewed["filter_series"])
        self.assertEqual(viewed["row_count"], 1)
        self.assertEqual(viewed["via"], "org")

        with capture_logs() as logs:
            self._internal({"organization": self.org.pk})
        (viewed,) = [e for e in logs if e["event"] == "signup_ledger_viewed"]
        self.assertEqual(viewed["via"], "internal")
