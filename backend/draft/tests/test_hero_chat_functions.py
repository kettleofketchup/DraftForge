import ast
import random
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from unittest import mock

import redis
from django.contrib.auth.models import AnonymousUser
from django.db import connection
from django.db.models import Q
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from structlog.testing import capture_logs

from app.models import CustomUser, Game, Team, Tournament
from draft.models import (
    HeroDraft,
    HeroDraftChatMembership,
    HeroDraftChatMessage,
    HeroDraftRound,
    HeroDraftState,
)
from draft.services import hero, hero_chat, heroes
from draft.services.hero import new_herodraft_for_game
from draft.services.hero_chat import (
    ALL_RATE_LIMIT_MAX,
    RATE_LIMIT_MAX,
    RATE_LIMIT_WINDOW_S,
    SPECTATOR,
    ChatError,
    ChatViewer,
    PostResult,
    check_rate_limit,
    close_membership,
    normalize_chat_text,
    open_membership,
    parse_composer,
    post_suggestion,
    post_text,
    rate_limit_channel,
    rate_limit_key,
    resolve_chat_viewer,
    serialize_message,
    team_group_name,
    visible_messages,
    withdraw_suggestion,
)
from league.models import League
from org.models import Organization

Channel = HeroDraftChatMessage.Channel
Kind = HeroDraftChatMessage.Kind


class ChatFixtureMixin:
    def setUp(self) -> None:
        def user(name: str, **kw: Any) -> CustomUser:
            return CustomUser.objects.create_user(username=name, password="x", **kw)

        self.cap_a = user("cf_cap_a")
        self.mem_a = user("cf_mem_a")
        self.cap_b = user("cf_cap_b")
        self.mem_b = user("cf_mem_b")
        self.outsider = user("cf_outsider")
        self.both = user("cf_both")
        self.dropin = user("cf_dropin")
        self.left = user("cf_left")
        self.superuser = CustomUser.objects.create_superuser(
            username="cf_super", password="x"
        )
        self.staff = user("cf_staff", is_staff=True)
        self.org_admin = user("cf_org_admin")
        self.league_staff = user("cf_league_staff")

        org = Organization.objects.create(name="Chat Fn Org")
        org.admins.add(self.org_admin)
        league = League.objects.create(name="Chat Fn League", organization=org)
        league.staff.add(self.league_staff)
        self.tournament = Tournament.objects.create(
            name="Chat Fn Tournament", date_played=date.today(), league=league
        )
        self.team_a = Team.objects.create(
            name="CF A", tournament=self.tournament, captain=self.cap_a
        )
        self.team_b = Team.objects.create(
            name="CF B", tournament=self.tournament, captain=self.cap_b
        )
        self.team_a.members.add(self.mem_a, self.both)
        self.team_b.members.add(self.mem_b, self.both)
        self.team_a.dropin_members.add(self.dropin)
        self.team_a.left_members.add(self.left)
        self.game = Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.team_a,
            dire_team=self.team_b,
        )
        self.draft: HeroDraft = new_herodraft_for_game(self.game)

    def msg(self, **kwargs: Any) -> HeroDraftChatMessage:
        fields: dict[str, Any] = {
            "draft": self.draft,
            "channel": Channel.TEAM,
            "team": self.team_a,
            "sender": self.cap_a,
            "kind": Kind.TEXT,
            "body": "hello",
        }
        fields.update(kwargs)
        return HeroDraftChatMessage.objects.create(**fields)

    def all_msg(
        self, body: str, sender: CustomUser | None = None
    ) -> HeroDraftChatMessage:
        return self.msg(
            channel=Channel.ALL, team=None, body=body, sender=sender or self.cap_b
        )

    def bodies(self, viewer: ChatViewer) -> list[str]:
        return [m["body"] for m in visible_messages(self.draft.pk, viewer)]


class ChatFixture(ChatFixtureMixin, TestCase):
    pass


class ResolveChatViewerTest(ChatFixture):
    def resolve(self, user: CustomUser | AnonymousUser | None) -> ChatViewer:
        return resolve_chat_viewer(self.draft.pk, user)

    def assert_spectator(self, viewer: ChatViewer) -> None:
        self.assertEqual(viewer.role, "spectator")
        self.assertIsNone(viewer.team_id)
        self.assertIsNone(viewer.joined_at)
        self.assertFalse(viewer.can_post_team)
        self.assertFalse(viewer.can_post_all)

    def test_none_is_spectator(self) -> None:
        self.assertEqual(self.resolve(None), SPECTATOR)
        self.assertIsNone(SPECTATOR.user_id)

    def test_anonymous_is_spectator(self) -> None:
        self.assertEqual(self.resolve(AnonymousUser()), SPECTATOR)

    def test_outsider_is_spectator(self) -> None:
        viewer = self.resolve(self.outsider)
        self.assert_spectator(viewer)
        self.assertEqual(viewer.user_id, self.outsider.pk)

    def test_captain_not_in_members_is_member(self) -> None:
        self.assertFalse(self.team_a.members.filter(pk=self.cap_a.pk).exists())
        viewer = self.resolve(self.cap_a)
        self.assertEqual(viewer.role, "member")
        self.assertEqual(viewer.team_id, self.team_a.pk)
        self.assertTrue(viewer.can_post_team)
        self.assertTrue(viewer.can_post_all)
        self.assertIsNotNone(viewer.joined_at)

    def test_plain_member_is_member(self) -> None:
        viewer = self.resolve(self.mem_b)
        self.assertEqual(viewer.role, "member")
        self.assertEqual(viewer.team_id, self.team_b.pk)

    def test_both_rosters_is_ambiguous_and_logged(self) -> None:
        with capture_logs() as logs:
            viewer = self.resolve(self.both)
        self.assertEqual(viewer.role, "ambiguous")
        self.assertIsNone(viewer.team_id)
        self.assertFalse(viewer.can_post_team)
        self.assertFalse(viewer.can_post_all)
        warned = [
            e for e in logs if e["event"] == "herodraft_chat_ambiguous_membership"
        ]
        self.assertEqual(len(warned), 1)
        self.assertEqual(warned[0]["log_level"], "warning")
        self.assertEqual(warned[0]["system"], "herodraft")
        self.assertEqual(warned[0]["subsystem"], "chat")

    def test_captain_of_one_member_of_other_is_ambiguous(self) -> None:
        self.team_b.members.add(self.cap_a)
        self.assertEqual(self.resolve(self.cap_a).role, "ambiguous")

    def test_dropin_only_is_spectator(self) -> None:
        self.assert_spectator(self.resolve(self.dropin))

    def test_left_member_only_is_spectator(self) -> None:
        self.assert_spectator(self.resolve(self.left))

    def test_staff_roles_are_spectators(self) -> None:
        for user in (self.superuser, self.staff, self.org_admin, self.league_staff):
            with self.subTest(user=user.username):
                self.assert_spectator(self.resolve(user))

    def test_as_payload(self) -> None:
        viewer = self.resolve(self.mem_a)
        self.assertEqual(
            viewer.as_payload(),
            {
                "role": "member",
                "team_id": self.team_a.pk,
                "can_post_team": True,
                "can_post_all": True,
            },
        )
        self.assertEqual(
            SPECTATOR.as_payload(),
            {
                "role": "spectator",
                "team_id": None,
                "can_post_team": False,
                "can_post_all": False,
            },
        )

    def test_resolve_keeps_existing_open_row(self) -> None:
        joined = self.draft.created_at
        open_membership(self.draft.pk, self.team_a.pk, self.mem_a.pk, joined)
        viewer = self.resolve(self.mem_a)
        self.assertEqual(viewer.joined_at, joined)
        self.assertEqual(
            HeroDraftChatMembership.objects.filter(
                draft=self.draft, user=self.mem_a
            ).count(),
            1,
        )

    def test_resolve_reconciles_team_switch(self) -> None:
        joined = self.draft.created_at
        open_membership(self.draft.pk, self.team_b.pk, self.mem_a.pk, joined)
        before = timezone.now()
        viewer = self.resolve(self.mem_a)

        self.assertEqual(viewer.team_id, self.team_a.pk)
        old = HeroDraftChatMembership.objects.get(
            draft=self.draft, user=self.mem_a, team=self.team_b
        )
        self.assertIsNotNone(old.left_at)
        new = HeroDraftChatMembership.objects.get(
            draft=self.draft, user=self.mem_a, left_at__isnull=True
        )
        self.assertEqual(new.team_id, self.team_a.pk)
        self.assertGreaterEqual(new.joined_at, before)
        self.assertEqual(viewer.joined_at, new.joined_at)

    def test_spectator_resolution_closes_stale_open_row(self) -> None:
        open_membership(
            self.draft.pk, self.team_a.pk, self.outsider.pk, self.draft.created_at
        )
        self.assertEqual(self.resolve(self.outsider).role, "spectator")
        self.assertFalse(
            HeroDraftChatMembership.objects.filter(
                draft=self.draft, user=self.outsider, left_at__isnull=True
            ).exists()
        )


class ResolveNocacheTest(ChatFixtureMixin, TransactionTestCase):
    """TransactionTestCase: cacheops does not cache inside TestCase's open transaction."""

    def test_resolve_uses_nocache(self) -> None:
        uid = self.outsider.pk
        warm = (
            Team.objects.filter(hero_draft_teams__draft_id=self.draft.pk)
            .filter(Q(captain_id=uid) | Q(members=uid))
            .values_list("pk", flat=True)
            .distinct()
        )
        self.assertEqual(list(warm), [])
        self.assertEqual(
            resolve_chat_viewer(self.draft.pk, self.outsider).role, "spectator"
        )

        through = Team.members.through
        with connection.cursor() as cursor:
            cursor.execute(
                f"INSERT INTO {through._meta.db_table} "
                f"({through._meta.get_field('team').column}, "
                f"{through._meta.get_field('customuser').column}) VALUES (%s, %s)",
                [self.team_a.pk, uid],
            )
        self.assertEqual(list(warm.all()), [], "cacheops must serve the stale result")
        before = timezone.now()
        viewer = resolve_chat_viewer(self.draft.pk, self.outsider)
        after = timezone.now()

        self.assertEqual(viewer.role, "member")
        self.assertEqual(viewer.team_id, self.team_a.pk)
        row = HeroDraftChatMembership.objects.get(
            draft=self.draft, user=self.outsider, left_at__isnull=True
        )
        self.assertEqual(row.team_id, self.team_a.pk)
        self.assertTrue(before <= row.joined_at <= after)
        self.assertEqual(viewer.joined_at, row.joined_at)


class SpectatorResolveWritesTest(ChatFixture):
    def test_spectator_without_open_row_issues_no_write(self) -> None:
        with CaptureQueriesContext(connection) as ctx:
            viewer = resolve_chat_viewer(self.draft.pk, self.outsider)
        self.assertEqual(viewer.role, "spectator")
        writes = [
            q["sql"]
            for q in ctx.captured_queries
            if q["sql"].lstrip().upper().startswith(("UPDATE", "INSERT", "DELETE"))
        ]
        self.assertEqual(writes, [])


class MembershipHelpersTest(ChatFixture):
    def open_rows(self, user: CustomUser) -> list[HeroDraftChatMembership]:
        return list(
            HeroDraftChatMembership.objects.filter(
                draft=self.draft, user=user, left_at__isnull=True
            )
        )

    def test_open_same_team_is_noop(self) -> None:
        t0 = self.draft.created_at
        open_membership(self.draft.pk, self.team_a.pk, self.mem_a.pk, t0)
        open_membership(
            self.draft.pk, self.team_a.pk, self.mem_a.pk, t0 + timedelta(hours=1)
        )
        rows = self.open_rows(self.mem_a)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].joined_at, t0)

    def test_open_other_team_closes_first(self) -> None:
        t0 = self.draft.created_at
        t1 = t0 + timedelta(minutes=5)
        open_membership(self.draft.pk, self.team_b.pk, self.mem_a.pk, t0)
        open_membership(self.draft.pk, self.team_a.pk, self.mem_a.pk, t1)
        old = HeroDraftChatMembership.objects.get(user=self.mem_a, team=self.team_b)
        self.assertEqual(old.left_at, t1)
        rows = self.open_rows(self.mem_a)
        self.assertEqual(
            [(r.team_id, r.joined_at) for r in rows], [(self.team_a.pk, t1)]
        )

    def test_closed_row_never_reopened(self) -> None:
        t0 = self.draft.created_at
        t1 = t0 + timedelta(minutes=5)
        open_membership(self.draft.pk, self.team_a.pk, self.mem_a.pk, t0)
        close_membership(self.draft.pk, self.mem_a.pk)
        open_membership(self.draft.pk, self.team_a.pk, self.mem_a.pk, t1)
        rows = HeroDraftChatMembership.objects.filter(user=self.mem_a).order_by("id")
        self.assertEqual(rows.count(), 2)
        self.assertIsNotNone(rows[0].left_at)
        self.assertEqual(rows[1].joined_at, t1)
        self.assertIsNone(rows[1].left_at)

    def test_close_with_at(self) -> None:
        t0 = self.draft.created_at
        at = t0 + timedelta(minutes=3)
        open_membership(self.draft.pk, self.team_a.pk, self.mem_a.pk, t0)
        close_membership(self.draft.pk, self.mem_a.pk, at=at)
        self.assertEqual(
            HeroDraftChatMembership.objects.get(user=self.mem_a).left_at, at
        )

    def test_close_respects_team_filter(self) -> None:
        open_membership(
            self.draft.pk, self.team_a.pk, self.mem_a.pk, self.draft.created_at
        )
        close_membership(self.draft.pk, self.mem_a.pk, team_id=self.team_b.pk)
        self.assertEqual(len(self.open_rows(self.mem_a)), 1)
        close_membership(self.draft.pk, self.mem_a.pk, team_id=self.team_a.pk)
        self.assertEqual(self.open_rows(self.mem_a), [])


class ParseComposerTest(TestCase):
    PARITY: list[tuple[str, tuple[str, str]]] = [
        ("/all x", ("all", "x")),
        ("/ALL  x ", ("all", "x")),
        ("/allx", ("team", "/allx")),
        ("/all", ("all", "")),
        ("   hi", ("team", "hi")),
        ("/all\x1fx", ("team", "/allx")),
        ("/all\tx", ("all", "x")),
        ("/all\u00a0x", ("team", "/all\u00a0x")),
        ("a\nb", ("team", "a b")),
        ("\x00\x07", ("team", "")),
        ("a\u2028b\u2029c", ("team", "a b c")),
        ("\u200b/all x", ("all", "x")),
        ("/all\u202ex", ("team", "/allx")),
    ]

    def test_parity_table(self) -> None:
        for raw, expected in self.PARITY:
            with self.subTest(raw=raw):
                self.assertEqual(parse_composer(raw), expected)

    def test_normalize_strips_c0_c1_and_newlines(self) -> None:
        self.assertEqual(normalize_chat_text("a\r\nb\x85c\x7fd\x9f"), "a  bcd")
        self.assertEqual(normalize_chat_text("tab\tkept"), "tab\tkept")

    def test_normalize_strips_format_and_line_separators(self) -> None:
        self.assertEqual(normalize_chat_text("a\u2028b\u2029c"), "a b c")
        bidi = "".join(chr(c) for c in [*range(0x202A, 0x202F), *range(0x2066, 0x206A)])
        self.assertEqual(normalize_chat_text(f"x{bidi}y"), "xy")
        self.assertEqual(normalize_chat_text("a\u200bb\u2060c\ufeffd\u00ade"), "abcde")
        self.assertEqual(
            normalize_chat_text("\U0001f468\u200d\U0001f469"),
            "\U0001f468\u200d\U0001f469",
        )
        self.assertEqual(
            normalize_chat_text("\u0645\u200c\u06cc"), "\u0645\u200c\u06cc"
        )

    def test_case_insensitive_prefix(self) -> None:
        self.assertEqual(parse_composer("/All gl hf"), ("all", "gl hf"))
        self.assertEqual(parse_composer("  /aLL\t\tgg"), ("all", "gg"))


class VisibleMessagesTest(ChatFixture):
    def test_member_sees_all_and_own_team_only(self) -> None:
        self.all_msg("all-1")
        self.msg(body="a-team-1")
        self.msg(team=self.team_b, sender=self.cap_b, body="b-team-1")

        member_a = resolve_chat_viewer(self.draft.pk, self.mem_a)
        self.assertEqual(member_a.role, "member")
        # Lazily opened at now(); push it back so the earlier rows fall inside tenure.
        HeroDraftChatMembership.objects.filter(user=self.mem_a).update(
            joined_at=self.draft.created_at
        )
        member_a = resolve_chat_viewer(self.draft.pk, self.mem_a)
        self.assertEqual(self.bodies(member_a), ["all-1", "a-team-1"])

    def test_spectator_and_ambiguous_see_all_only(self) -> None:
        self.all_msg("all-1")
        self.msg(body="a-team-secret")
        self.msg(team=self.team_b, sender=self.cap_b, body="b-team-secret")
        for user in (None, self.outsider, self.both, self.superuser, self.org_admin):
            with self.subTest(user=getattr(user, "username", None)):
                viewer = resolve_chat_viewer(self.draft.pk, user)
                self.assertEqual(self.bodies(viewer), ["all-1"])

    def test_message_before_joined_at_excluded(self) -> None:
        early = self.msg(body="before-join")
        HeroDraftChatMessage.objects.filter(pk=early.pk).update(
            created_at=timezone.now() - timedelta(minutes=10)
        )
        open_membership(
            self.draft.pk,
            self.team_a.pk,
            self.mem_a.pk,
            timezone.now() - timedelta(minutes=5),
        )
        self.msg(body="after-join")
        viewer = resolve_chat_viewer(self.draft.pk, self.mem_a)
        self.assertEqual(self.bodies(viewer), ["after-join"])

    def test_forged_member_viewer_for_other_team_sees_nothing_extra(self) -> None:
        self.msg(body="a-secret")
        forged = ChatViewer(
            user_id=self.outsider.pk,
            team_id=self.team_a.pk + self.team_b.pk + 1000,
            role="member",
            joined_at=self.draft.created_at,
        )
        self.assertEqual(self.bodies(forged), [])

    def test_repoint_hides_old_team_chat_from_everyone(self) -> None:
        self.all_msg("all-1")
        self.msg(body="old-a-secret")
        open_membership(
            self.draft.pk, self.team_a.pk, self.mem_a.pk, self.draft.created_at
        )
        stale_viewer = resolve_chat_viewer(self.draft.pk, self.mem_a)
        self.assertIn("old-a-secret", self.bodies(stale_viewer))

        cap_c = CustomUser.objects.create_user(username="cf_cap_c", password="x")
        team_c = Team.objects.create(
            name="CF C", tournament=self.tournament, captain=cap_c
        )
        self.game.radiant_team = team_c
        self.game.save()

        self.assertNotIn("old-a-secret", self.bodies(stale_viewer))
        for user in (self.mem_a, self.cap_a, cap_c, self.outsider, None):
            with self.subTest(user=getattr(user, "username", None)):
                viewer = resolve_chat_viewer(self.draft.pk, user)
                self.assertEqual(self.bodies(viewer), ["all-1"])
        self.assertEqual(resolve_chat_viewer(self.draft.pk, cap_c).team_id, team_c.pk)

    def test_oldest_to_newest_and_limit_returns_newest(self) -> None:
        for i in range(105):
            self.all_msg(f"m{i:03d}")
        result = self.bodies(SPECTATOR)
        self.assertEqual(len(result), 100)
        self.assertEqual(result[0], "m005")
        self.assertEqual(result[-1], "m104")
        self.assertEqual(
            [m["body"] for m in visible_messages(self.draft.pk, SPECTATOR, limit=3)],
            ["m102", "m103", "m104"],
        )

    def test_other_draft_messages_excluded(self) -> None:
        other_game = Game.objects.create(
            tournament=self.tournament, radiant_team=self.team_a, dire_team=self.team_b
        )
        other = new_herodraft_for_game(other_game)
        HeroDraftChatMessage.objects.create(
            draft=other, channel=Channel.ALL, sender=self.cap_a, body="other-draft"
        )
        self.all_msg("this-draft")
        self.assertEqual(self.bodies(SPECTATOR), ["this-draft"])


class SerializeMessageTest(ChatFixture):
    ALLOWED_INT_PATHS = {("team_id",), ("hero_id",), ("sender", "pk")}

    def walk(
        self, value: Any, path: tuple[str, ...]
    ) -> list[tuple[tuple[str, ...], Any]]:
        if isinstance(value, dict):
            out: list[tuple[tuple[str, ...], Any]] = []
            for k, v in value.items():
                out += self.walk(v, (*path, k))
            return out
        if isinstance(value, list):
            out = []
            for i, v in enumerate(value):
                out += self.walk(v, (*path, str(i)))
            return out
        return [(path, value)]

    def test_shape(self) -> None:
        msg = self.msg(kind=Kind.SUGGEST_BAN, hero_id=74, body="")
        data = serialize_message(msg)
        self.assertEqual(
            set(data),
            {
                "id",
                "channel",
                "team_id",
                "kind",
                "hero_id",
                "body",
                "created_at",
                "sender",
            },
        )
        self.assertEqual(data["id"], str(msg.public_id))
        self.assertEqual(data["channel"], "team")
        self.assertEqual(data["team_id"], self.team_a.pk)
        self.assertEqual(data["kind"], "suggest_ban")
        self.assertEqual(data["hero_id"], 74)
        self.assertEqual(data["body"], "")
        self.assertTrue(
            re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z", data["created_at"]),
            data["created_at"],
        )
        self.assertTrue(
            {"pk", "username", "nickname", "avatarUrl", "discordId"}
            <= set(data["sender"])
        )
        self.assertEqual(data["sender"]["pk"], self.cap_a.pk)
        self.assertEqual(data["sender"]["username"], self.cap_a.username)

    def test_all_chat_nulls_present(self) -> None:
        data = serialize_message(self.all_msg("hi"))
        self.assertIsNone(data["team_id"])
        self.assertIsNone(data["hero_id"])

    def test_no_integer_ids_outside_allowlist(self) -> None:
        data = serialize_message(self.msg(kind=Kind.SUGGEST_PICK, hero_id=1, body=""))
        for path, value in self.walk(data, ()):
            if isinstance(value, int) and not isinstance(value, bool):
                self.assertIn(path, self.ALLOWED_INT_PATHS, path)
            if path != ("sender", "pk"):
                self.assertNotIn(path[-1], {"pk", "client_msg_id"}, path)


class TeamGroupNameTest(TestCase):
    def test_format(self) -> None:
        self.assertEqual(team_group_name(1, 2), "herodraft_1_team_2")

    def test_channel_layer_rules(self) -> None:
        name = team_group_name(2_147_483_647, 2_147_483_647)
        self.assertRegex(name, r"^[a-zA-Z\d\-_.]+$")
        self.assertLess(len(name), 100)


class PostingFixture(ChatFixture):
    def viewer(self, user: CustomUser) -> ChatViewer:
        return resolve_chat_viewer(self.draft.pk, user)

    def set_state(self, state: str) -> None:
        self.draft.state = state
        self.draft.save()

    def assert_code(self, code: str, fn: Any, *args: Any) -> None:
        with self.assertRaises(ChatError) as ctx:
            fn(*args)
        self.assertEqual(ctx.exception.code, code)
        self.assertEqual(HeroDraftChatMessage.objects.count(), 0)


class PostTextTest(PostingFixture):
    def post(self, user: CustomUser, raw: str) -> PostResult:
        return post_text(self.draft.pk, user, raw, self.viewer(user))

    def test_team_text_persists_on_own_team(self) -> None:
        result = self.post(self.mem_a, "  push mid ")
        row = HeroDraftChatMessage.objects.get()
        self.assertEqual(row.channel, Channel.TEAM)
        self.assertEqual(row.team_id, self.team_a.pk)
        self.assertEqual(row.sender_id, self.mem_a.pk)
        self.assertEqual(row.kind, Kind.TEXT)
        self.assertEqual(row.body, "push mid")
        self.assertIsNone(row.hero_id)
        self.assertEqual(result.channel, "team")
        self.assertEqual(result.team_id, self.team_a.pk)
        self.assertEqual(result.viewer.team_id, self.team_a.pk)
        self.assertEqual(result.message, serialize_message(row))

    def test_captain_of_b_posts_to_b(self) -> None:
        self.post(self.cap_b, "hi")
        self.assertEqual(HeroDraftChatMessage.objects.get().team_id, self.team_b.pk)

    def test_all_prefix_routes_to_all(self) -> None:
        result = self.post(self.cap_a, "/all gl")
        row = HeroDraftChatMessage.objects.get()
        self.assertEqual(row.channel, Channel.ALL)
        self.assertIsNone(row.team_id)
        self.assertEqual(row.body, "gl")
        self.assertEqual(result.channel, "all")
        self.assertIsNone(result.team_id)
        self.assertEqual(result.message["channel"], "all")

    def test_empty_bodies(self) -> None:
        for raw in ("", "/all", "   ", "/ALL \t ", "\x00\x07"):
            with self.subTest(raw=raw):
                self.assert_code("empty", self.post, self.mem_a, raw)

    def test_too_long(self) -> None:
        self.assert_code("too_long", self.post, self.mem_a, "x" * 501)
        self.assert_code("too_long", self.post, self.mem_a, "/all " + "x" * 501)

    def test_non_string_body_bad_request(self) -> None:
        for raw in (None, 5, ["hi"], {"body": "hi"}):
            with self.subTest(raw=raw):
                self.assert_code("bad_request", self.post, self.mem_a, raw)

    def test_500_chars_accepted(self) -> None:
        self.post(self.mem_a, "x" * 500)
        self.assertEqual(len(HeroDraftChatMessage.objects.get().body), 500)

    def test_all_prefix_not_counted_in_length(self) -> None:
        result = self.post(self.mem_a, "/all " + "x" * 500)
        self.assertEqual(result.channel, "all")
        self.assertEqual(HeroDraftChatMessage.objects.get().body, "x" * 500)

    def test_spectators_cannot_post(self) -> None:
        for user in (
            self.outsider,
            self.superuser,
            self.staff,
            self.org_admin,
            self.league_staff,
            self.dropin,
            self.left,
        ):
            for raw in ("hi", "/all hi"):
                with self.subTest(user=user.username, raw=raw):
                    self.assert_code("not_participant", self.post, user, raw)

    def test_anonymous_spectator_cannot_post(self) -> None:
        self.assert_code(
            "not_participant", post_text, self.draft.pk, self.outsider, "hi", SPECTATOR
        )

    def test_viewer_for_another_user_rejected(self) -> None:
        self.assert_code(
            "not_participant",
            post_text,
            self.draft.pk,
            self.mem_b,
            "hi",
            self.viewer(self.mem_a),
        )

    def test_ambiguous_checked_before_not_participant(self) -> None:
        for raw in ("hi", "/all hi", ""):
            with self.subTest(raw=raw):
                self.assert_code("ambiguous_team", self.post, self.both, raw)

    def test_terminal_states_closed(self) -> None:
        for state in (HeroDraftState.COMPLETED, HeroDraftState.ABANDONED):
            with self.subTest(state=state):
                self.set_state(state)
                self.assert_code("draft_closed", self.post, self.mem_a, "hi")
                self.assert_code("draft_closed", self.post, self.mem_a, "/all hi")

    def test_non_terminal_states_accepted(self) -> None:
        states = (
            HeroDraftState.WAITING_FOR_CAPTAINS,
            HeroDraftState.ROLLING,
            HeroDraftState.CHOOSING,
            HeroDraftState.DRAFTING,
            HeroDraftState.PAUSED,
            HeroDraftState.RESUMING,
        )
        for state in states:
            with self.subTest(state=state):
                self.set_state(state)
                self.post(self.mem_a, f"in {state}")
        self.assertEqual(HeroDraftChatMessage.objects.count(), len(states))

    def test_state_read_bypasses_stale_instance(self) -> None:
        HeroDraft.objects.filter(pk=self.draft.pk).update(
            state=HeroDraftState.COMPLETED
        )
        self.assert_code("draft_closed", self.post, self.mem_a, "hi")


class PostSuggestionTest(PostingFixture):
    def setUp(self) -> None:
        super().setUp()
        self.set_state(HeroDraftState.DRAFTING)

    def suggest(self, user: CustomUser, kind: str, hero_id: object) -> PostResult:
        return post_suggestion(self.draft.pk, user, kind, hero_id, self.viewer(user))

    def use_hero(self, hero_id: int, action: str) -> None:
        HeroDraftRound.objects.create(
            draft=self.draft,
            draft_team=self.draft.draft_teams.first(),
            round_number=HeroDraftRound.objects.filter(draft=self.draft).count() + 1,
            action_type=action,
            hero_id=hero_id,
            state="completed",
        )

    def test_suggestion_persists_on_team(self) -> None:
        for kind in (Kind.SUGGEST_PICK, Kind.SUGGEST_BAN):
            with self.subTest(kind=kind):
                result = self.suggest(self.mem_a, kind, 74)
                row = HeroDraftChatMessage.objects.get(public_id=result.message["id"])
                self.assertEqual(row.kind, kind)
                self.assertEqual(row.hero_id, 74)
                self.assertEqual(row.body, "")
                self.assertEqual(row.channel, Channel.TEAM)
                self.assertEqual(row.team_id, self.team_a.pk)
                self.assertEqual(result.channel, "team")
                self.assertEqual(result.team_id, self.team_a.pk)

    def test_picked_or_banned_hero_unavailable(self) -> None:
        self.use_hero(74, "pick")
        self.use_hero(1, "ban")
        for hero_id in (74, 1):
            with self.subTest(hero_id=hero_id):
                self.assert_code(
                    "hero_unavailable",
                    self.suggest,
                    self.mem_a,
                    Kind.SUGGEST_BAN,
                    hero_id,
                )

    def test_bad_hero_ids(self) -> None:
        for hero_id in (0, 999, -1, "74", None, True, 74.0, [74]):
            with self.subTest(hero_id=hero_id):
                self.assert_code(
                    "hero_unavailable",
                    self.suggest,
                    self.mem_a,
                    Kind.SUGGEST_PICK,
                    hero_id,
                )

    def test_bad_kind(self) -> None:
        for kind in ("text", "x", "", None, ["suggest_pick"], {"k": 1}):
            with self.subTest(kind=kind):
                self.assert_code("bad_request", self.suggest, self.mem_a, kind, 74)

    def test_non_drafting_states_inactive(self) -> None:
        for state in (
            HeroDraftState.WAITING_FOR_CAPTAINS,
            HeroDraftState.ROLLING,
            HeroDraftState.CHOOSING,
            HeroDraftState.PAUSED,
            HeroDraftState.RESUMING,
        ):
            with self.subTest(state=state):
                self.set_state(state)
                self.assert_code(
                    "draft_inactive", self.suggest, self.mem_a, Kind.SUGGEST_PICK, 74
                )

    def test_terminal_states_closed(self) -> None:
        for state in (HeroDraftState.COMPLETED, HeroDraftState.ABANDONED):
            with self.subTest(state=state):
                self.set_state(state)
                self.assert_code(
                    "draft_closed", self.suggest, self.mem_a, Kind.SUGGEST_PICK, 74
                )

    def test_spectator_cannot_suggest(self) -> None:
        for user in (self.outsider, self.superuser, self.org_admin):
            with self.subTest(user=user.username):
                self.assert_code(
                    "not_participant", self.suggest, user, Kind.SUGGEST_PICK, 74
                )

    def test_ambiguous_cannot_suggest(self) -> None:
        self.assert_code(
            "ambiguous_team", self.suggest, self.both, Kind.SUGGEST_PICK, 74
        )


class WithdrawSuggestionTest(PostingFixture):
    def setUp(self) -> None:
        super().setUp()
        self.set_state(HeroDraftState.DRAFTING)

    def suggest(self, user: CustomUser, kind: str, hero_id: int) -> PostResult:
        return post_suggestion(self.draft.pk, user, kind, hero_id, self.viewer(user))

    def withdraw(self, user: CustomUser, kind: object, hero_id: object) -> PostResult:
        return withdraw_suggestion(
            self.draft.pk, user, kind, hero_id, self.viewer(user)
        )

    def assert_code(self, code: str, fn: Any, *args: Any) -> None:
        before = HeroDraftChatMessage.objects.count()
        with self.assertRaises(ChatError) as ctx:
            fn(*args)
        self.assertEqual(ctx.exception.code, code)
        self.assertEqual(HeroDraftChatMessage.objects.count(), before)

    def test_withdraw_persists_matching_kind(self) -> None:
        pairs = (
            (Kind.SUGGEST_PICK, Kind.UNSUGGEST_PICK),
            (Kind.SUGGEST_BAN, Kind.UNSUGGEST_BAN),
        )
        for kind, withdrawn in pairs:
            with self.subTest(kind=kind):
                self.suggest(self.mem_a, kind, 74)
                result = self.withdraw(self.mem_a, kind, 74)
                row = HeroDraftChatMessage.objects.get(public_id=result.message["id"])
                self.assertEqual(row.kind, withdrawn)
                self.assertEqual(row.hero_id, 74)
                self.assertEqual(row.channel, Channel.TEAM)
                self.assertEqual(row.team_id, self.team_a.pk)

    def test_requires_an_active_own_suggestion(self) -> None:
        self.assert_code(
            "not_suggested", self.withdraw, self.mem_a, Kind.SUGGEST_PICK, 74
        )
        self.suggest(self.mem_a, Kind.SUGGEST_BAN, 74)
        self.assert_code(
            "not_suggested", self.withdraw, self.mem_a, Kind.SUGGEST_PICK, 74
        )
        self.suggest(self.cap_a, Kind.SUGGEST_PICK, 74)
        self.assert_code(
            "not_suggested", self.withdraw, self.mem_a, Kind.SUGGEST_PICK, 74
        )
        self.suggest(self.mem_a, Kind.SUGGEST_PICK, 74)
        self.withdraw(self.mem_a, Kind.SUGGEST_PICK, 74)
        self.assert_code(
            "not_suggested", self.withdraw, self.mem_a, Kind.SUGGEST_PICK, 74
        )

    def test_bad_kind_or_hero(self) -> None:
        for kind in ("text", "unsuggest_pick", None, ["suggest_pick"]):
            with self.subTest(kind=kind):
                self.assert_code("bad_request", self.withdraw, self.mem_a, kind, 74)
        for hero_id in ("74", None, True, 74.0):
            with self.subTest(hero_id=hero_id):
                self.assert_code(
                    "bad_request",
                    self.withdraw,
                    self.mem_a,
                    Kind.SUGGEST_PICK,
                    hero_id,
                )

    def test_non_drafting_states_inactive(self) -> None:
        self.suggest(self.mem_a, Kind.SUGGEST_PICK, 74)
        self.set_state(HeroDraftState.PAUSED)
        self.assert_code(
            "draft_inactive", self.withdraw, self.mem_a, Kind.SUGGEST_PICK, 74
        )

    def test_spectator_cannot_withdraw(self) -> None:
        self.assert_code(
            "not_participant", self.withdraw, self.outsider, Kind.SUGGEST_PICK, 74
        )


class RateLimitTest(SimpleTestCase):
    def setUp(self) -> None:
        self.draft_id = random.randint(10**8, 10**9)
        self.user_id = random.randint(10**8, 10**9)
        self.key = rate_limit_key(self.draft_id, self.user_id)
        self.all_key = rate_limit_key(self.draft_id, self.user_id, "all")
        self.redis = hero_chat.get_redis_client()
        self.redis.delete(self.key, self.all_key)

    def tearDown(self) -> None:
        self.redis.delete(self.key, self.all_key)

    def test_limits(self) -> None:
        self.assertEqual(RATE_LIMIT_MAX, 8)
        self.assertEqual(ALL_RATE_LIMIT_MAX, 4)
        self.assertEqual(RATE_LIMIT_WINDOW_S, 10)

    def test_rate_limit_channel(self) -> None:
        self.assertEqual(rate_limit_channel("chat_send", {"body": "/all gg"}), "all")
        self.assertEqual(rate_limit_channel("chat_send", {"body": "gg"}), "team")
        self.assertEqual(rate_limit_channel("chat_send", {"body": 5}), "team")
        self.assertEqual(
            rate_limit_channel("chat_suggest", {"body": "/all x", "kind": "pick"}),
            "team",
        )

    def test_all_chat_bucket_is_separate_key(self) -> None:
        self.assertNotEqual(self.key, self.all_key)
        self.assertEqual(rate_limit_key(self.draft_id, self.user_id, "team"), self.key)

    def test_fifth_all_chat_call_rate_limited(self) -> None:
        for _ in range(ALL_RATE_LIMIT_MAX):
            check_rate_limit(self.draft_id, self.user_id, "all")
        with self.assertRaises(ChatError) as ctx:
            check_rate_limit(self.draft_id, self.user_id, "all")
        self.assertEqual(ctx.exception.code, "rate_limited")
        self.assertLessEqual(self.redis.ttl(self.all_key), RATE_LIMIT_WINDOW_S)

    def test_all_chat_flood_leaves_team_bucket_untouched(self) -> None:
        for _ in range(ALL_RATE_LIMIT_MAX):
            check_rate_limit(self.draft_id, self.user_id, "all")
        for _ in range(RATE_LIMIT_MAX):
            check_rate_limit(self.draft_id, self.user_id, "team")
        with self.assertRaises(ChatError):
            check_rate_limit(self.draft_id, self.user_id, "all")
        with self.assertRaises(ChatError):
            check_rate_limit(self.draft_id, self.user_id)

    def test_all_chat_redis_unavailable_fails_closed(self) -> None:
        with (
            mock.patch.object(
                hero_chat,
                "get_redis_client",
                side_effect=redis.ConnectionError("down"),
            ),
            self.assertRaises(ChatError) as ctx,
        ):
            check_rate_limit(self.draft_id, self.user_id, "all")
        self.assertEqual(ctx.exception.code, "unavailable")

    def test_ninth_call_rate_limited(self) -> None:
        for _ in range(RATE_LIMIT_MAX):
            check_rate_limit(self.draft_id, self.user_id)
        with self.assertRaises(ChatError) as ctx:
            check_rate_limit(self.draft_id, self.user_id)
        self.assertEqual(ctx.exception.code, "rate_limited")

    def test_users_and_drafts_isolated(self) -> None:
        for _ in range(RATE_LIMIT_MAX):
            check_rate_limit(self.draft_id, self.user_id)
        others = [
            rate_limit_key(self.draft_id, self.user_id + 1),
            rate_limit_key(self.draft_id + 1, self.user_id),
        ]
        try:
            check_rate_limit(self.draft_id, self.user_id + 1)
            check_rate_limit(self.draft_id + 1, self.user_id)
        finally:
            self.redis.delete(*others)

    def test_ttl_set_once_and_never_extended(self) -> None:
        check_rate_limit(self.draft_id, self.user_id)
        first = self.redis.ttl(self.key)
        self.assertGreaterEqual(first, 1)
        self.assertLessEqual(first, RATE_LIMIT_WINDOW_S)
        for _ in range(11):
            try:
                check_rate_limit(self.draft_id, self.user_id)
            except ChatError:
                pass
            self.assertGreater(self.redis.ttl(self.key), 0)
        self.assertLessEqual(self.redis.ttl(self.key), first)
        self.assertEqual(int(self.redis.get(self.key)), 12)

    def test_redis_unavailable_fails_closed(self) -> None:
        with (
            mock.patch.object(
                hero_chat,
                "get_redis_client",
                side_effect=redis.ConnectionError("down"),
            ),
            capture_logs() as logs,
            self.assertRaises(ChatError) as ctx,
        ):
            check_rate_limit(self.draft_id, self.user_id)
        self.assertEqual(ctx.exception.code, "unavailable")
        events = [
            e
            for e in logs
            if e["event"] == "herodraft_chat_rate_limit_redis_unavailable"
        ]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["system"], "herodraft")
        self.assertEqual(events[0]["subsystem"], "chat")

    def test_pipeline_error_fails_closed(self) -> None:
        client = mock.Mock()
        client.pipeline.return_value.execute.side_effect = redis.TimeoutError("slow")
        with (
            mock.patch.object(hero_chat, "get_redis_client", return_value=client),
            capture_logs() as logs,
            self.assertRaises(ChatError) as ctx,
        ):
            check_rate_limit(self.draft_id, self.user_id)
        self.assertEqual(ctx.exception.code, "unavailable")
        self.assertTrue(
            any(
                e["event"] == "herodraft_chat_rate_limit_redis_unavailable"
                for e in logs
            )
        )
        client.pipeline.assert_called_once_with(transaction=True)


class HeroesModuleIsLeafTest(SimpleTestCase):
    FORBIDDEN = "draft.services.hero"

    def imports(self, path: Path) -> set[str]:
        names: set[str] = set()
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module)
                names.update(f"{node.module}.{alias.name}" for alias in node.names)
        return names

    def test_heroes_module_is_leaf(self) -> None:
        services = Path(hero_chat.__file__).resolve().parent
        for name in ("heroes.py", "hero_chat.py"):
            with self.subTest(module=name):
                imported = self.imports(services / name)
                self.assertNotIn(self.FORBIDDEN, imported)
        self.assertLessEqual(
            {
                m
                for m in self.imports(services / "heroes.py")
                if m.startswith(("app", "draft", "tournament"))
            },
            {"draft.models", "draft.models.HeroDraft"},
        )

    def test_herodraft_reexports_moved_names(self) -> None:
        self.assertIs(hero.get_available_heroes, heroes.get_available_heroes)
        self.assertIs(hero.ALL_HERO_IDS, heroes.ALL_HERO_IDS)
