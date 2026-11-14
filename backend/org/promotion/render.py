import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TypedDict

from django.conf import settings

from app.models import CustomUser, Organization
from common.discord_format import discord_timestamp
from events.models import Event


class PlaceholderSpec(TypedDict):
    key: str
    description: str


PLACEHOLDERS: tuple[PlaceholderSpec, ...] = (
    {
        "key": "player",
        "description": "Recipient's server nickname, Discord name or site nickname",
    },
    {"key": "promoter", "description": "Your name"},
    {"key": "event", "description": "Event name"},
    {
        "key": "event_time",
        "description": "Full start date and time, shown in the reader's timezone",
    },
    {"key": "event_time_relative", "description": "Time until start (in 3 days)"},
    {"key": "event_date", "description": "Start date only"},
    {
        "key": "signups_open",
        "description": "Time until sign-ups open, empty if not set",
    },
    {"key": "event_link", "description": "Link to the event page"},
    {"key": "org", "description": "Organization name"},
    {"key": "discord_link", "description": "Organization's Discord invite link"},
)

TOKEN_RE = re.compile(
    r"\{(player|promoter|event|event_time|event_time_relative|event_date"
    r"|signups_open|event_link|org|discord_link)\}"
)
ANY_TOKEN_RE = re.compile(r"\{[^{}]*\}")

UNBALANCED_BRACE = "unbalanced brace"


@dataclass(frozen=True)
class RenderResult:
    text: str
    warnings: list[str] = field(default_factory=list)


def _scan_warnings(body: str) -> list[str]:
    warnings: list[str] = []
    for match in ANY_TOKEN_RE.finditer(body):
        token = match[0]
        if TOKEN_RE.fullmatch(token) is None:
            warning = f"unknown placeholder {token}"
            if warning not in warnings:
                warnings.append(warning)
    leftover = ANY_TOKEN_RE.sub("", body)
    if "{" in leftover or "}" in leftover:
        warnings.append(UNBALANCED_BRACE)
    return warnings


def validate_template_body(body: str) -> list[str]:
    return _scan_warnings(body)


def render_template(body: str, context: Mapping[str, str]) -> RenderResult:
    text = TOKEN_RE.sub(lambda m: context[m[1]], body)
    return RenderResult(text=text, warnings=_scan_warnings(body))


def player_name(user: CustomUser) -> str:
    for candidate in (
        user.guildNickname,
        user.discordNickname,
        user.discordUsername,
        user.nickname,
    ):
        if candidate:
            return candidate
    return user.username


def build_context(
    *,
    event: Event,
    recipient: CustomUser,
    sender: CustomUser,
    org: Organization,
) -> dict[str, str]:
    signups_open = (
        discord_timestamp(event.signups_open_at, "R") if event.signups_open_at else ""
    )
    return {
        "player": player_name(recipient),
        "promoter": player_name(sender),
        "event": event.name,
        "event_time": discord_timestamp(event.scheduled_at, "F"),
        "event_time_relative": discord_timestamp(event.scheduled_at, "R"),
        "event_date": discord_timestamp(event.scheduled_at, "D"),
        "signups_open": signups_open,
        "event_link": f"{settings.SITE_URL}/events/{event.pk}",
        "org": org.name,
        "discord_link": org.discord_link or "",
    }
