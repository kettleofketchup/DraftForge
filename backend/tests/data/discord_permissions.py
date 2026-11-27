"""Discord permission badge E2E test data.

Used by frontend/tests/playwright/e2e/events/discord-permission-badges.spec.ts.
Created by tests.populate.discord_permissions.populate_discord_permissions_data.

- Org / league 70 "Permission Badges Org" / "Permission Badges League", with
  the synthetic Discord server 900000000000000070.
- Users 9100 org staff, 9101 league staff only, 9102 outsider.
- Two otherwise identical future events: a fresh one with no Discord rows and
  a posted one with a DiscordEvent and a posted signup thread.
- PERMISSION_SCENARIOS: canned Discord GET responses the TEST-only fixture
  source serves (discordbot.permissions.reader.FixtureSource).
"""

from copy import deepcopy
from typing import Any, Final

from discordbot.permissions.flags import BIT
from discordbot.permissions.flags import PermissionFlag as F
from tests.data.models import TestLeague, TestOrganization, TestUser

PERMISSION_GUILD_ID: Final[str] = "900000000000000070"
PERMISSION_BOT_ID: Final[str] = "900000000000000071"
PERMISSION_OWNER_ID: Final[str] = "900000000000000072"
PERMISSION_BOT_ROLE_ID: Final[str] = "900000000000000073"
PERMISSION_ANNOUNCEMENT_CHANNEL_ID: Final[str] = "900000000000000074"
PERMISSION_ATTENDANCE_CHANNEL_ID: Final[str] = "900000000000000075"
PERMISSION_HISTORY_CHANNEL_ID: Final[str] = "900000000000000076"
PERMISSION_HISTORY_THREAD_ID: Final[str] = "900000000000000077"
PERMISSION_SIGNUP_MESSAGE_ID: Final[str] = "900000000000000078"
PERMISSION_SCHEDULED_EVENT_ID: Final[str] = "900000000000000079"

PERMISSION_ORG: TestOrganization = TestOrganization(
    pk=70,
    name="Permission Badges Org",
    description="Isolated organization for the Discord permission badge E2E tests.",
    timezone="America/New_York",
    discord_server_id=PERMISSION_GUILD_ID,
)
PERMISSION_LEAGUE: TestLeague = TestLeague(
    pk=70,
    name="Permission Badges League",
    steam_league_id=17970,
    organization_names=[PERMISSION_ORG.name],
)

PERMISSION_FRESH_EVENT_NAME: Final[str] = "Permission Badges Fresh Event"
PERMISSION_POSTED_EVENT_NAME: Final[str] = "Permission Badges Posted Event"
PERMISSION_EVENT_NAMES: Final[tuple[str, ...]] = (
    PERMISSION_FRESH_EVENT_NAME,
    PERMISSION_POSTED_EVENT_NAME,
)

_DISCORD_BASE: Final[int] = 900_000_000_000_000_000


def _user(pk: int, username: str, nickname: str) -> TestUser:
    return TestUser(
        pk=pk,
        username=username,
        nickname=nickname,
        discord_id=str(_DISCORD_BASE + pk),
    )


PERMISSION_STAFF: TestUser = _user(9100, "perm_staff", "Perm Staff")
PERMISSION_LEAGUE_STAFF: TestUser = _user(
    9101, "perm_league_staff", "Perm League Staff"
)
PERMISSION_OUTSIDER: TestUser = _user(9102, "perm_outsider", "Perm Outsider")
PERMISSION_USERS: Final[tuple[TestUser, ...]] = (
    PERMISSION_STAFF,
    PERMISSION_LEAGUE_STAFF,
    PERMISSION_OUTSIDER,
)

PERMISSION_DEFAULT_SCENARIO: Final[str] = "attendance_missing_embed"


def _bits(*flags: F) -> str:
    return str(sum(BIT[flag] for flag in flags))


_BOT_GRANTS: Final[tuple[F, ...]] = (
    F.VIEW_CHANNEL,
    F.SEND_MESSAGES,
    F.SEND_MESSAGES_IN_THREADS,
    F.EMBED_LINKS,
    F.READ_MESSAGE_HISTORY,
    F.ADD_REACTIONS,
    F.CREATE_EVENTS,
    F.MANAGE_EVENTS,
)


def _text_channel(
    channel_id: str, name: str, overwrites: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return {
        "id": channel_id,
        "guild_id": PERMISSION_GUILD_ID,
        "type": 0,
        "name": name,
        "permission_overwrites": overwrites or [],
    }


def _all_granted() -> dict[str, Any]:
    g, b = PERMISSION_GUILD_ID, PERMISSION_BOT_ID
    thread, message = PERMISSION_HISTORY_THREAD_ID, PERMISSION_SIGNUP_MESSAGE_ID
    return {
        "/users/@me": {"id": b},
        f"/guilds/{g}": {
            "id": g,
            "owner_id": PERMISSION_OWNER_ID,
            "roles": [
                {
                    "id": g,
                    "permissions": _bits(F.VIEW_CHANNEL),
                    "mentionable": False,
                    "managed": False,
                },
                {
                    "id": PERMISSION_BOT_ROLE_ID,
                    "permissions": _bits(*_BOT_GRANTS),
                    "mentionable": False,
                    "managed": True,
                },
            ],
        },
        f"/guilds/{g}/members/{b}": {
            "user": {"id": b},
            "roles": [PERMISSION_BOT_ROLE_ID],
            "communication_disabled_until": None,
        },
        f"/guilds/{g}/channels": [
            _text_channel(PERMISSION_ANNOUNCEMENT_CHANNEL_ID, "announcements"),
            _text_channel(PERMISSION_ATTENDANCE_CHANNEL_ID, "attendance"),
            _text_channel(PERMISSION_HISTORY_CHANNEL_ID, "signup-history"),
        ],
        f"/channels/{thread}": {
            "id": thread,
            "guild_id": g,
            "type": 11,
            "name": "signups",
            "parent_id": PERMISSION_HISTORY_CHANNEL_ID,
            "thread_metadata": {"archived": False, "locked": False},
        },
        f"/channels/{thread}/messages/{message}": {
            "id": message,
            "channel_id": thread,
            "author": {"id": b},
        },
        f"/guilds/{g}/scheduled-events/{PERMISSION_SCHEDULED_EVENT_ID}": {
            "id": PERMISSION_SCHEDULED_EVENT_ID,
            "guild_id": g,
            "creator_id": b,
        },
    }


def _deny_on(
    data: dict[str, Any], channel_id: str, target_id: str, *flags: F
) -> dict[str, Any]:
    for channel in data[f"/guilds/{PERMISSION_GUILD_ID}/channels"]:
        if channel["id"] == channel_id:
            channel["permission_overwrites"].append(
                {"id": target_id, "type": 0, "allow": "0", "deny": _bits(*flags)}
            )
    return data


def _without_bot_grant(data: dict[str, Any], flag: F) -> dict[str, Any]:
    for role in data[f"/guilds/{PERMISSION_GUILD_ID}"]["roles"]:
        if role["id"] == PERMISSION_BOT_ROLE_ID:
            role["permissions"] = str(int(role["permissions"]) & ~BIT[flag])
    return data


def _attendance_missing_embed() -> dict[str, Any]:
    return _deny_on(
        _all_granted(),
        PERMISSION_ATTENDANCE_CHANNEL_ID,
        PERMISSION_BOT_ROLE_ID,
        F.EMBED_LINKS,
    )


def _no_create_events() -> dict[str, Any]:
    return _without_bot_grant(_all_granted(), F.CREATE_EVENTS)


def _edit_access_denied() -> dict[str, Any]:
    data = _deny_on(
        _all_granted(),
        PERMISSION_HISTORY_CHANNEL_ID,
        PERMISSION_GUILD_ID,
        F.VIEW_CHANNEL,
    )
    return _deny_on(
        data, PERMISSION_HISTORY_CHANNEL_ID, PERMISSION_BOT_ROLE_ID, F.VIEW_CHANNEL
    )


def _upstream_unavailable() -> dict[str, Any]:
    data = _all_granted()
    data[f"/guilds/{PERMISSION_GUILD_ID}"] = {"status": 503, "body": None}
    return data


_SCENARIOS: Final[dict[str, dict[str, Any]]] = {
    "all_granted": _all_granted(),
    "attendance_missing_embed": _attendance_missing_embed(),
    "no_create_events": _no_create_events(),
    "edit_access_denied": _edit_access_denied(),
    "upstream_unavailable": _upstream_unavailable(),
}
PERMISSION_SCENARIO_NAMES: Final[frozenset[str]] = frozenset(_SCENARIOS)


def permission_scenario(name: str) -> dict[str, Any]:
    """A fresh copy of the named scenario; KeyError for unknown names."""
    return deepcopy(_SCENARIOS[name])
