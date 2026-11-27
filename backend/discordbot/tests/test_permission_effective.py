from dataclasses import replace
from datetime import UTC, datetime, timedelta

import discord
from django.test import SimpleTestCase

from discordbot.permissions.effective import channel_permissions, guild_permissions
from discordbot.permissions.flags import (
    ALL_KNOWN,
    BIT,
    CHANNEL_SCOPED_MASK,
    PermissionFlag,
    labels,
)
from discordbot.permissions.schemas import (
    ChannelSnap,
    GuildSnap,
    MemberSnap,
    Overwrite,
    RoleSnap,
    ThreadMeta,
)

GUILD = "100000000000000001"
BOT = "100000000000000002"
ROLE_A = "100000000000000003"
ROLE_B = "100000000000000004"
NOW = datetime(2026, 11, 26, 12, tzinfo=UTC)


def bits(*names: str) -> int:
    result = 0
    for name in names:
        result |= BIT[PermissionFlag(name)]
    return result


def snap(
    everyone: int = 0,
    role_a: int = 0,
    role_b: int = 0,
    overwrites: tuple[Overwrite, ...] = (),
) -> tuple[GuildSnap, MemberSnap, ChannelSnap]:
    guild = GuildSnap(
        id=GUILD,
        owner_id="100000000000000009",
        roles={
            role_id: RoleSnap(role_id, permissions, False, False)
            for role_id, permissions in (
                (GUILD, everyone),
                (ROLE_A, role_a),
                (ROLE_B, role_b),
            )
        },
    )
    member = MemberSnap(BOT, (ROLE_A, ROLE_B), None)
    channel = ChannelSnap(
        id="100000000000000005",
        guild_id=GUILD,
        type=0,
        name="event-updates",
        parent_id=None,
        overwrites=overwrites,
        flags=0,
        thread_meta=None,
        available_tags_required=False,
    )
    return guild, member, channel


class EffectivePermissionTests(SimpleTestCase):
    def test_everyone_plus_multiple_roles_or_together(self) -> None:
        guild, member, _ = snap(
            bits("VIEW_CHANNEL"), bits("SEND_MESSAGES"), bits("CREATE_EVENTS")
        )
        result = guild_permissions(guild, member, NOW)
        self.assertTrue(result.complete)
        self.assertEqual(
            result.bits, bits("VIEW_CHANNEL", "SEND_MESSAGES", "CREATE_EVENTS")
        )

    def test_missing_assigned_role_is_incomplete(self) -> None:
        guild, member, _ = snap(role_a=bits("ADMINISTRATOR"))
        guild = replace(
            guild,
            roles={key: role for key, role in guild.roles.items() if key != ROLE_B},
        )
        result = guild_permissions(guild, member, NOW)
        self.assertFalse(result.complete)
        self.assertIsNone(result.bits)
        self.assertEqual(result.incomplete_reason, "malformed_snapshot")

    def test_owner_gets_all_known(self) -> None:
        guild, member, _ = snap()
        result = guild_permissions(replace(guild, owner_id=BOT), member, NOW)
        self.assertEqual(result.bits, ALL_KNOWN)
        self.assertEqual(result.bypass, "owner")

    def test_administrator_bypasses_overwrites(self) -> None:
        guild, member, channel = snap(
            role_a=bits("ADMINISTRATOR"),
            overwrites=(Overwrite(GUILD, 0, 0, bits("VIEW_CHANNEL")),),
        )
        result = channel_permissions(guild, member, channel, None, NOW)
        self.assertEqual(result.bits, ALL_KNOWN)
        self.assertEqual(result.bypass, "administrator")

    def test_overwrite_order_everyone_then_roles_then_member(self) -> None:
        send, embed = bits("SEND_MESSAGES"), bits("EMBED_LINKS")
        guild, member, channel = snap(
            bits("VIEW_CHANNEL"),
            overwrites=(
                Overwrite(GUILD, 0, 0, send),
                Overwrite(ROLE_A, 0, send, embed),
                Overwrite(ROLE_B, 0, 0, send),
                Overwrite(BOT, 1, embed, 0),
            ),
        )
        result = channel_permissions(guild, member, channel, None, NOW)
        self.assertEqual(
            result.bits, bits("VIEW_CHANNEL", "SEND_MESSAGES", "EMBED_LINKS")
        )
        denied = replace(
            channel, overwrites=channel.overwrites + (Overwrite(BOT, 1, 0, send),)
        )
        self.assertFalse(channel_permissions(guild, member, denied, None, NOW).complete)

    def test_role_position_irrelevant(self) -> None:
        guild, member, channel = snap(
            bits("VIEW_CHANNEL"), bits("SEND_MESSAGES"), bits("EMBED_LINKS")
        )
        self.assertEqual(
            channel_permissions(guild, member, channel, None, NOW),
            channel_permissions(
                guild,
                replace(member, role_ids=tuple(reversed(member.role_ids))),
                channel,
                None,
                NOW,
            ),
        )

    def test_no_view_channel_clears_channel_bits(self) -> None:
        guild, member, channel = snap(
            ALL_KNOWN & ~bits("ADMINISTRATOR", "VIEW_CHANNEL")
        )
        result = channel_permissions(guild, member, channel, None, NOW)
        self.assertEqual(result.bits & CHANNEL_SCOPED_MASK, 0)
        self.assertTrue(
            guild_permissions(guild, member, NOW).bits
            & bits("CREATE_EVENTS", "MANAGE_EVENTS")
        )

    def test_no_send_clears_send_dependents(self) -> None:
        guild, member, channel = snap(
            bits("VIEW_CHANNEL", "EMBED_LINKS", "MENTION_EVERYONE", "ATTACH_FILES")
        )
        self.assertEqual(
            channel_permissions(guild, member, channel, None, NOW).bits,
            bits("VIEW_CHANNEL"),
        )

    def test_thread_uses_parent_overwrites_and_thread_send_bit(self) -> None:
        guild, member, parent = snap(
            bits(
                "VIEW_CHANNEL",
                "SEND_MESSAGES",
                "SEND_MESSAGES_IN_THREADS",
                "EMBED_LINKS",
            ),
            overwrites=(Overwrite(GUILD, 0, 0, bits("SEND_MESSAGES")),),
        )
        thread = replace(
            parent,
            id="100000000000000006",
            type=11,
            parent_id=parent.id,
            overwrites=(),
            thread_meta=ThreadMeta(False, False, False, None),
        )
        result = channel_permissions(guild, member, thread, parent, NOW)
        self.assertTrue(result.bits & bits("SEND_MESSAGES_IN_THREADS"))
        self.assertTrue(result.bits & bits("EMBED_LINKS"))
        self.assertFalse(result.bits & bits("SEND_MESSAGES"))

    def test_thread_missing_parent_is_incomplete(self) -> None:
        guild, member, channel = snap()
        thread = replace(channel, type=11, parent_id="100000000000000006")
        for parent in (
            None,
            channel,
            replace(channel, id=thread.parent_id, guild_id="100000000000000099"),
        ):
            with self.subTest(parent=parent):
                result = channel_permissions(guild, member, thread, parent, NOW)
                self.assertFalse(result.complete)
                self.assertIsNone(result.bits)
                self.assertEqual(result.incomplete_reason, "malformed_snapshot")

    def test_guild_event_bits_ignore_channel_overwrites(self) -> None:
        guild, member, channel = snap(
            bits("VIEW_CHANNEL", "CREATE_EVENTS"),
            overwrites=(Overwrite(GUILD, 0, 0, bits("CREATE_EVENTS")),),
        )
        self.assertTrue(
            guild_permissions(guild, member, NOW).bits & bits("CREATE_EVENTS")
        )
        self.assertTrue(
            channel_permissions(guild, member, channel, None, NOW).bits
            & bits("CREATE_EVENTS")
        )

    def test_timeout_cases(self) -> None:
        grants = bits(
            "VIEW_CHANNEL", "READ_MESSAGE_HISTORY", "SEND_MESSAGES", "CREATE_EVENTS"
        )
        cases = (
            (
                NOW + timedelta(minutes=1),
                False,
                False,
                grants,
                bits("VIEW_CHANNEL", "READ_MESSAGE_HISTORY"),
                True,
            ),
            (NOW + timedelta(minutes=1), False, False, bits("CREATE_EVENTS"), 0, True),
            (NOW - timedelta(seconds=1), False, False, grants, grants, False),
            (None, False, False, grants, grants, False),
            (NOW + timedelta(minutes=1), True, False, grants, ALL_KNOWN, False),
            (NOW + timedelta(minutes=1), False, True, grants, ALL_KNOWN, False),
        )
        for until, owner, admin, base, expected, timed_out in cases:
            with self.subTest(until=until, owner=owner, admin=admin, base=base):
                guild, member, channel = snap(
                    base,
                    bits("ADMINISTRATOR") if admin else 0,
                    overwrites=(Overwrite(BOT, 1, bits("SEND_MESSAGES"), 0),),
                )
                guild = replace(guild, owner_id=BOT) if owner else guild
                member = replace(member, communication_disabled_until=until)
                result = guild_permissions(guild, member, NOW)
                self.assertEqual(result.bits, expected)
                self.assertEqual(result.timeout_until, until if timed_out else None)
                self.assertEqual(
                    result.base_bits, ALL_KNOWN if owner or admin else base
                )
                if timed_out:
                    self.assertFalse(
                        channel_permissions(guild, member, channel, None, NOW).bits
                        & bits("SEND_MESSAGES")
                    )
        guild, member, channel = snap(grants)
        for until in ("malformed", datetime(2026, 11, 26, 13)):
            with self.subTest(malformed=until):
                member = replace(member, communication_disabled_until=until)
                for result in (
                    guild_permissions(guild, member, NOW),
                    channel_permissions(guild, member, channel, None, NOW),
                ):
                    self.assertFalse(result.complete)
                    self.assertIsNone(result.bits)
                    self.assertEqual(result.incomplete_reason, "malformed_snapshot")

    def test_catalogue_matches_discord_py(self) -> None:
        self.assertEqual(ALL_KNOWN, discord.Permissions.all().value)
        self.assertEqual(CHANNEL_SCOPED_MASK, discord.Permissions.all_channel().value)
        self.assertEqual(BIT[PermissionFlag.CREATE_EVENTS], 1 << 44)
        self.assertEqual(BIT[PermissionFlag.SEND_MESSAGES_IN_THREADS], 1 << 38)

    def test_unknown_future_bits_retained_in_raw(self) -> None:
        guild, member, channel = snap(bits("VIEW_CHANNEL") | 1 << 60)
        result = channel_permissions(guild, member, channel, None, NOW)
        self.assertEqual(result.bits, bits("VIEW_CHANNEL") | 1 << 60)
        self.assertEqual(labels(result.bits), ["VIEW_CHANNEL"])
