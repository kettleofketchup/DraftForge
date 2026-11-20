import re
from datetime import date, timedelta
from typing import Any

from django.contrib.auth.models import AnonymousUser
from django.db import connection
from django.db.models import Q
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from structlog.testing import capture_logs

from app.functions.herodraft import new_herodraft_for_game
from app.functions.herodraft_chat import (
    SPECTATOR,
    ChatViewer,
    close_membership,
    normalize_chat_text,
    open_membership,
    parse_composer,
    resolve_chat_viewer,
    serialize_message,
    team_group_name,
    visible_messages,
)
from app.models import (
    CustomUser,
    Game,
    HeroDraft,
    HeroDraftChatMembership,
    HeroDraftChatMessage,
    League,
    Organization,
    Team,
    Tournament,
)

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
    ]

    def test_parity_table(self) -> None:
        for raw, expected in self.PARITY:
            with self.subTest(raw=raw):
                self.assertEqual(parse_composer(raw), expected)

    def test_normalize_strips_c0_c1_and_newlines(self) -> None:
        self.assertEqual(normalize_chat_text("a\r\nb\x85c\x7fd\x9f"), "a  bcd")
        self.assertEqual(normalize_chat_text("tab\tkept"), "tab\tkept")

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
