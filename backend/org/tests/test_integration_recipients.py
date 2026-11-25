"""Authorized event-recipient pages for the promotion integration.

GET ``/api/organizations/{org}/integration/v1/events/{event}/recipients/``
lists every subject DraftForge would let a promoter contact for the event:
org members, recent and active players at the widest windows, guild
candidates (including Discord-only identities with no account), local send
recipients and prior imported recipients. It never enrolls anyone. Pages are
keyset-ordered and their signed cursors are bound to the org, the event and
the ``mapping_version`` of the whole universe; a changed universe is 409
``mapping_changed`` so the adaptor re-fetches from the first page.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

from django.core.cache import cache
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser
from config.promotion_sync import PromotionSyncConfig
from discordbot.services.discord_members import DiscordMembersFetchError
from events.models import Event, EventSignup
from org.api_tokens.tokens import issue_token
from org.integration.cursors import encode_cursor
from org.integration.subjects import authorized_event_subjects
from org.models import Organization, OrgUser, PromoSend
from org.models_promotion_sync import (
    ContactLinkage,
    ContactMethod,
    ExternalPromotionReceipt,
    ReceiptSource,
)
from org.tests.test_api_tokens import LOCMEM_CACHE
from org.tests.test_promotion_api import PromotionApiBase
from tournament.models import Tournament

GUILD = "770000000000000001"
FETCH = "org.promotion.recipients.get_discord_members_data"
GUILD_ONLY_ID = "990000000000000001"
IMPORTED_ONLY_ID = "990000000000000002"


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


def bindings(org: Organization, *events: Event) -> PromotionSyncConfig:
    raw = json.dumps(
        [
            {
                "org_id": str(org.pk),
                "guild_id": GUILD,
                "events": [
                    {"event_id": str(e.pk), "occasion_id": str(88 + i)}
                    for i, e in enumerate(events)
                ],
            }
        ]
    )
    return PromotionSyncConfig.from_env(environ={"PROMOTION_SYNC_BINDINGS": raw})


@override_settings(CACHES=LOCMEM_CACHE, DISCORD_BOT_TOKEN="test-bot-token")
class _RecipientsBase(PromotionApiBase):
    def setUp(self) -> None:
        super().setUp()
        cache.clear()
        self.org.discord_server_id = GUILD
        self.org.save()
        self.admin = self.users["admin"]
        assert self.admin is not None
        self.issued = issue_token(
            self.org, self.admin, "adaptor", operations=["promotion:read"]
        )
        self.members: list[dict[str, Any]] = []
        self._settings = override_settings(
            PROMOTION_SYNC=bindings(self.org, self.event, self.completed_event)
        )
        self._settings.enable()
        self.addCleanup(self._settings.disable)
        fetch = patch(FETCH, side_effect=lambda **_: list(self.members))
        self.fetch = fetch.start()
        self.addCleanup(fetch.stop)

    def bearer(self, raw: str | None = None) -> APIClient:
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {raw or self.issued.raw}")
        return client

    def url(self, event: Event | None = None, org: Organization | None = None) -> str:
        return (
            f"/api/organizations/{(org or self.org).pk}/integration/v1/events/"
            f"{(event or self.event).pk}/recipients/"
        )

    def get(self, params: dict[str, Any] | None = None, **kwargs: Any):
        return self.bearer(kwargs.pop("raw", None)).get(
            self.url(**kwargs), params or {}
        )

    def all_pages(self, limit: int = 100) -> tuple[list[dict], str]:
        seen: list[dict] = []
        cursor: str | None = None
        version = None
        while True:
            params: dict[str, Any] = {"limit": limit}
            if cursor:
                params["cursor"] = cursor
            resp = self.get(params)
            self.assertEqual(resp.status_code, 200, resp.content)
            body = resp.json()
            self.assertEqual(
                set(body), {"mapping_version", "recipients", "next_cursor"}
            )
            version = version or body["mapping_version"]
            self.assertEqual(body["mapping_version"], version)
            seen.extend(body["recipients"])
            cursor = body["next_cursor"]
            if cursor is None:
                return seen, version

    def tuples(self, rows: list[dict]) -> set[tuple]:
        return {(r["user_id"], r["org_user_id"], r["discord_id"]) for r in rows}

    def row(self, user: CustomUser) -> tuple:
        ou = OrgUser.objects.filter(user=user, organization=self.org).first()
        return (str(user.pk), str(ou.pk) if ou else None, user.discordId)

    def assertError(self, resp, status: int, code: str) -> None:
        self.assertEqual(resp.status_code, status, resp.content)
        self.assertEqual(resp.json()["error"]["code"], code)


class UniverseTests(_RecipientsBase):
    def test_universe_includes_member_recent_active_guild_local_and_imported_history(
        self,
    ) -> None:
        member_no_discord = CustomUser.objects.create_user(
            username="nodc", password="x"
        )
        OrgUser.objects.create(user=member_no_discord, organization=self.org)

        recent_player = self._user("recent_player")
        old = Tournament.objects.create(
            name="Older",
            date_played=timezone.now() - timedelta(days=200),
            league=self.league,
        )
        old.users.add(recent_player)

        active = self._user("active_far")
        signup = EventSignup.objects.create(event=self.completed_event, user=active)
        EventSignup.objects.filter(pk=signup.pk).update(
            signed_up_at=timezone.now() - timedelta(days=80)
        )

        linked_joiner = self._user("linked_joiner")
        self.members = [
            guild_member(GUILD_ONLY_ID, days_ago=60),
            guild_member(linked_joiner.discordId, days_ago=1),
            guild_member("990000000000000009", days_ago=1, bot=True),
        ]

        sent_to = self._user("sent_to")
        PromoSend.objects.create(
            organization=self.org,
            event=self.event,
            recipient=sent_to,
            sender=self.users["promoter"],
            text="hi",
        )
        ExternalPromotionReceipt.objects.create(
            organization=self.org,
            source=ReceiptSource.CONTACT_LOG,
            source_contact_id=1,
            event=self.event,
            discord_id=IMPORTED_ONLY_ID,
            recorded_at=datetime(2026, 11, 1, tzinfo=UTC),
            contact_method=ContactMethod.DISCORD_DM,
            linkage=ContactLinkage.OCCASION,
            source_hash="a" * 64,
        )

        rows, version = self.all_pages()
        self.assertRegex(version, r"\A[0-9a-f]{64}\Z")
        member = self.users["member"]
        expected = {
            self.row(member),
            self.row(self.recipient),
            (str(member_no_discord.pk), self.row(member_no_discord)[1], None),
            self.row(active),
            self.row(linked_joiner),
            self.row(sent_to),
            (None, None, GUILD_ONLY_ID),
            (None, None, IMPORTED_ONLY_ID),
        }
        self.assertTrue(expected <= self.tuples(rows), self.tuples(rows) ^ expected)
        # Recent pool reaches only MAX_POOL_N most recent org tournaments; the
        # 200-day-old one is still among this org's two tournaments.
        self.assertIn(self.row(recent_player), self.tuples(rows))
        self.assertNotIn("990000000000000009", {r["discord_id"] for r in rows})
        self.assertEqual(len(rows), len(self.tuples(rows)))

    def test_contacted_and_signed_up_subjects_are_not_filtered(self) -> None:
        member = self.users["member"]
        EventSignup.objects.create(event=self.event, user=member)
        PromoSend.objects.create(
            organization=self.org,
            event=self.event,
            recipient=self.recipient,
            sender=self.users["promoter"],
            text="hi",
        )
        rows, _ = self.all_pages()
        self.assertTrue(
            {self.row(member), self.row(self.recipient)} <= self.tuples(rows)
        )

    def test_non_member_and_null_user_without_enrollment(self) -> None:
        self.members = [guild_member(GUILD_ONLY_ID, days_ago=1)]
        users, org_users = CustomUser.objects.count(), OrgUser.objects.count()
        with (
            patch(
                "org.promotion.recipients.user_for_guild_member",
                side_effect=AssertionError("enrollment"),
            ),
            patch(
                "org.membership.resolve_or_create_org_user",
                side_effect=AssertionError("enrollment"),
            ),
        ):
            rows, _ = self.all_pages()
        self.assertIn((None, None, GUILD_ONLY_ID), self.tuples(rows))
        self.assertEqual(CustomUser.objects.count(), users)
        self.assertEqual(OrgUser.objects.count(), org_users)

    def test_unrelated_global_user_not_authorized(self) -> None:
        stranger = self._user("stranger")
        other_player = self._user("other_org_player")
        elsewhere = Tournament.objects.create(
            name="Elsewhere", date_played=timezone.now() - timedelta(days=1)
        )
        elsewhere.users.add(other_player)
        OrgUser.objects.create(user=other_player, organization=self.other_org)
        rows, _ = self.all_pages()
        ids = {r["user_id"] for r in rows}
        self.assertNotIn(str(stranger.pk), ids)
        self.assertNotIn(str(other_player.pk), ids)

    def test_other_event_history_is_not_this_events_universe(self) -> None:
        ExternalPromotionReceipt.objects.create(
            organization=self.org,
            source=ReceiptSource.CONTACT_LOG,
            source_contact_id=2,
            event=self.completed_event,
            discord_id=IMPORTED_ONLY_ID,
            recorded_at=datetime(2026, 11, 1, tzinfo=UTC),
            contact_method=ContactMethod.DISCORD_DM,
            linkage=ContactLinkage.OCCASION,
            source_hash="b" * 64,
        )
        rows, _ = self.all_pages()
        self.assertNotIn(IMPORTED_ONLY_ID, {r["discord_id"] for r in rows})

    def test_known_subject_without_usable_discord_is_unresolved(self) -> None:
        odd = CustomUser.objects.create_user(
            username="odd", password="x", discordId="d-odd"
        )
        ou = OrgUser.objects.create(user=odd, organization=self.org)
        rows, _ = self.all_pages()
        self.assertIn((str(odd.pk), str(ou.pk), None), self.tuples(rows))

    def test_imported_discord_id_of_known_user_is_that_user(self) -> None:
        sent_to = self._user("imported_known")
        ExternalPromotionReceipt.objects.create(
            organization=self.org,
            source=ReceiptSource.CONTACT_LOG,
            source_contact_id=3,
            event=self.event,
            discord_id=sent_to.discordId,
            recorded_at=datetime(2026, 11, 1, tzinfo=UTC),
            contact_method=ContactMethod.DISCORD_DM,
            linkage=ContactLinkage.OCCASION,
            source_hash="c" * 64,
        )
        rows, _ = self.all_pages()
        matching = [r for r in rows if r["discord_id"] == sent_to.discordId]
        self.assertEqual(
            [(r["user_id"], r["org_user_id"]) for r in matching],
            [(str(sent_to.pk), None)],
        )

    def test_keyset_order_is_numeric_discord_then_user(self) -> None:
        short = CustomUser.objects.create_user(
            username="short", password="x", discordId="5"
        )
        OrgUser.objects.create(user=short, organization=self.org)
        no_dc = CustomUser.objects.create_user(username="nodc2", password="x")
        OrgUser.objects.create(user=no_dc, organization=self.org)
        rows, _ = self.all_pages()
        with_dc = [int(r["discord_id"]) for r in rows if r["discord_id"]]
        self.assertEqual(with_dc, sorted(with_dc))
        self.assertEqual(rows[0]["discord_id"], "5")
        tail = rows[len(with_dc) :]
        self.assertTrue(tail and all(r["discord_id"] is None for r in tail))
        tail_ids = [int(r["user_id"]) for r in tail]
        self.assertEqual(tail_ids, sorted(tail_ids))

    def test_service_reports_version_and_sorted_subjects(self) -> None:
        self.members = [guild_member(GUILD_ONLY_ID, days_ago=1)]
        universe = authorized_event_subjects(self.org, self.event)
        found = universe.by_discord_id(GUILD_ONLY_ID)
        self.assertEqual(
            (found.user_id, found.org_user_id, found.discord_id),
            (None, None, GUILD_ONLY_ID),
        )
        self.assertIsNone(universe.by_discord_id("990000000000000077"))
        recipient = universe.by_discord_id(self.recipient.discordId)
        self.assertEqual(recipient.user_id, self.recipient.pk)
        again = authorized_event_subjects(self.org, self.event)
        self.assertEqual(universe.mapping_version, again.mapping_version)
        keys = [s.sort_key() for s in universe.subjects]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(len(keys), len(set(keys)))


class SourceAvailabilityTests(_RecipientsBase):
    def test_missing_guild_source_is_unavailable_not_complete_empty(self) -> None:
        self.fetch.side_effect = DiscordMembersFetchError("boom 123456789012345678")
        resp = self.get()
        self.assertError(resp, 503, "subject_source_unavailable")
        self.assertNotIn("123456789012345678", resp.content.decode())

    def test_unconfigured_bot_token_is_unavailable(self) -> None:
        with override_settings(DISCORD_BOT_TOKEN=None):
            self.assertError(self.get(), 503, "subject_source_unavailable")
        self.fetch.assert_not_called()


class PagingTests(_RecipientsBase):
    def setUp(self) -> None:
        super().setUp()
        for i in range(4):
            user = self._user(f"pg_member_{i}")
            OrgUser.objects.create(user=user, organization=self.org)
        self.members = [guild_member(GUILD_ONLY_ID, days_ago=1)]

    def test_pages_no_duplicates_and_limit_bounds(self) -> None:
        full, version = self.all_pages(limit=100)
        one_by_one, version_1 = self.all_pages(limit=1)
        self.assertEqual(full, one_by_one)
        self.assertEqual(version, version_1)
        self.assertEqual(len(full), len(self.tuples(full)))
        default = self.get().json()
        self.assertEqual(default["recipients"], full)
        self.assertIsNone(default["next_cursor"])
        for bad in ("0", "101", "-1", "01", "1.0", "x", ""):
            with self.subTest(limit=bad):
                self.assertError(self.get({"limit": bad}), 400, "invalid_request")

    def test_unknown_or_repeated_query_parameters_rejected(self) -> None:
        self.assertError(self.get({"limit": "1", "q": "x"}), 400, "invalid_request")
        client = self.bearer()
        resp = client.get(self.url() + "?limit=1&limit=2")
        self.assertError(resp, 400, "invalid_request")

    def test_cursor_bound_to_org_event_universe(self) -> None:
        first = self.get({"limit": 1}).json()
        cursor = first["next_cursor"]
        self.assertTrue(cursor)
        self.assertLessEqual(len(cursor), 2048)

        other_event = self.bearer().get(
            self.url(event=self.completed_event), {"cursor": cursor}
        )
        self.assertError(other_event, 400, "invalid_cursor")
        self.assertError(self.get({"cursor": cursor + "x"}), 400, "invalid_cursor")
        self.assertError(self.get({"cursor": "a" * 2049}), 400, "invalid_cursor")
        self.assertError(self.get({"cursor": ""}), 400, "invalid_cursor")
        forged = encode_cursor(
            org_id=self.other_org.pk,
            resource=f"event_recipients:{self.event.pk}",
            key=[0, 1],
            fingerprint=first["mapping_version"],
        )
        self.assertError(self.get({"cursor": forged}), 400, "invalid_cursor")

        self.assertEqual(self.get({"cursor": cursor}).status_code, 200)
        OrgUser.objects.create(user=self._user("late_joiner"), organization=self.org)
        self.assertError(self.get({"cursor": cursor}), 409, "mapping_changed")
        fresh = self.get({"limit": 1}).json()
        self.assertNotEqual(fresh["mapping_version"], first["mapping_version"])

    def test_guild_identity_change_changes_mapping(self) -> None:
        first = self.get({"limit": 1}).json()
        self.members = []
        self.assertError(
            self.get({"cursor": first["next_cursor"]}), 409, "mapping_changed"
        )

    def test_binding_change_changes_mapping(self) -> None:
        first = self.get({"limit": 1}).json()
        with override_settings(PROMOTION_SYNC=bindings(self.org, self.event)):
            # event is still bound to occasion 88; dropping the other event
            # leaves its binding unchanged, so the version is stable.
            self.assertEqual(
                self.get({"cursor": first["next_cursor"]}).status_code, 200
            )
        with override_settings(
            PROMOTION_SYNC=bindings(self.org, self.completed_event, self.event)
        ):
            self.assertError(
                self.get({"cursor": first["next_cursor"]}), 409, "mapping_changed"
            )

    def test_query_count_does_not_grow_per_candidate(self) -> None:
        def count() -> int:
            cache.clear()
            with CaptureQueriesContext(connection) as ctx:
                self.assertEqual(self.get().status_code, 200)
            return len(ctx.captured_queries)

        count()  # the first request of the day creates the token usage row
        baseline = count()
        for i in range(8):
            user = self._user(f"qc_{i}")
            OrgUser.objects.create(user=user, organization=self.org)
            PromoSend.objects.create(
                organization=self.org,
                event=self.event,
                recipient=user,
                sender=self.users["promoter"],
                text="hi",
            )
        self.members = [
            guild_member(str(990000000000000100 + i), days_ago=1) for i in range(8)
        ]
        self.assertEqual(count(), baseline)


class AuthorizationTests(_RecipientsBase):
    def test_requires_promotion_read_grant(self) -> None:
        mmr = issue_token(self.org, self.admin, "mmr")
        self.assertError(self.get(raw=mmr.raw), 403, "operation_not_granted")
        importer = issue_token(
            self.org, self.admin, "imp", operations=["promotion:import"]
        )
        self.assertError(self.get(raw=importer.raw), 403, "operation_not_granted")

    def test_promotion_feature_required(self) -> None:
        self.lock()
        self.assertError(self.get(), 403, "feature_locked")

    def test_wrong_org_event_is_404(self) -> None:
        self.assertError(self.get(event=self.other_event), 404, "not_found")
        self.assertError(self.get(org=self.other_org), 404, "not_found")

    def test_unbound_event_is_binding_missing(self) -> None:
        unbound = Event.objects.create(
            organization=self.org,
            name="Unbound",
            scheduled_at=timezone.now() + timedelta(days=9),
            created_by=self.users["owner"],
        )
        self.assertError(self.get(event=unbound), 403, "binding_missing")

    def test_guild_mismatch_is_binding_mismatch(self) -> None:
        self.org.discord_server_id = "770000000000000002"
        self.org.save()
        self.assertError(self.get(), 403, "binding_mismatch")

    def test_session_and_missing_credentials_rejected(self) -> None:
        client = APIClient()
        self.assertError(client.get(self.url()), 401, "unauthorized")
        client.force_authenticate(self.admin)
        self.assertError(client.get(self.url()), 401, "unauthorized")

    def test_only_get_allowed(self) -> None:
        resp = self.bearer().post(self.url(), {}, format="json")
        self.assertError(resp, 405, "method_not_allowed")

    def test_errors_do_not_echo_identities(self) -> None:
        resp = self.get({"cursor": "not-a-cursor"})
        body = resp.content.decode()
        self.assertIsNone(re.search(r"\d{17,}", body))
