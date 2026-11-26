import time
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import replace
from datetime import datetime
from typing import Literal

from django.utils import timezone

from discordbot.permissions.actions import REGISTRY
from discordbot.permissions.evaluate import ResolvedCheck, SnapshotBundle, evaluate
from discordbot.permissions.reader import SnapshotReader, source_for
from discordbot.permissions.schemas import (
    ActionKind,
    ChannelSnap,
    Destination,
    Observation,
    PermissionCheckIn,
    PermissionChecksResponse,
    ReasonCode,
    ResolvedCheckInput,
)


def preview_checks(checks: list[PermissionCheckIn]) -> list[ResolvedCheckInput]:
    prospective = {
        ActionKind.START_MENTION,
        ActionKind.SCHEDULED_EVENT_UPDATE,
        ActionKind.SCHEDULED_EVENT_DELETE,
    }

    def source(
        check: PermissionCheckIn,
    ) -> Literal["configured", "fallback", "prospective"]:
        if check.action in prospective:
            return "prospective"
        if check.action == ActionKind.SIGNUP_FALLBACK or (
            check.fallback and REGISTRY[check.action].scope == "channel"
        ):
            return "fallback"
        return "configured"

    return [
        ResolvedCheckInput(
            key=check.key,
            action=check.action,
            destination_source=source(check),
            channel_id=check.channel_id,
            role_ids=tuple(check.role_ids),
            include_rsvp=check.include_rsvp,
            reference_present=False if check.action in prospective else None,
        )
        for check in checks
    ]


def run_checks(
    guild_id: str | None,
    checks: list[ResolvedCheckInput],
    *,
    refresh: bool,
    now: datetime | None = None,
) -> PermissionChecksResponse:
    if len(checks) > 20 or any(len(c.role_ids) > 25 for c in checks):
        raise ValueError("Permission batch exceeds limits")
    active = [c for c in checks if REGISTRY[c.action].scope in ("channel", "guild")]
    reader = SnapshotReader(source_for(guild_id)) if guild_id and active else None
    bundle = (
        reader.guild_bundle(guild_id, refresh)
        if reader and guild_id
        else SnapshotBundle(None, None, None, None, None)
    )
    channels: dict[str, tuple[ChannelSnap | None, ReasonCode | None]] = {}
    if reader and guild_id and not bundle.error:
        ids = {
            c.channel_id
            for c in active
            if REGISTRY[c.action].scope == "channel" and c.channel_id
        }
        if ids:
            reader._channels(guild_id, refresh)
            if time.monotonic() >= reader.deadline:
                channels = {cid: (None, "network_error") for cid in ids}
            else:
                executor = ThreadPoolExecutor(max_workers=4)
                futures = {
                    executor.submit(reader.channel, guild_id, cid, refresh): cid
                    for cid in ids
                }
                try:
                    done, pending = wait(
                        futures, timeout=max(0, reader.deadline - time.monotonic())
                    )
                    for future in done:
                        channels[futures[future]] = future.result()
                    for future in pending:
                        future.cancel()
                        channels[futures[future]] = (None, "network_error")
                finally:
                    executor.shutdown(wait=False, cancel_futures=True)
    results = []
    for check in checks:
        scope = REGISTRY[check.action].scope
        channel, error = channels.get(check.channel_id, (None, None))
        parent = None
        owned = None
        creator_is_bot = None
        dependencies: set[str] = set()
        if reader and guild_id and not bundle.error and scope in ("guild", "channel"):
            if check.channel_id:
                dependencies.update(
                    reader.channel_dependencies.get(check.channel_id, set())
                )
            if channel:
                if channel.type in (10, 11, 12) and channel.parent_id:
                    parent, parent_error = reader.channel(
                        guild_id, channel.parent_id, refresh
                    )
                    dependencies.update(
                        reader.channel_dependencies.get(channel.parent_id, set())
                    )
                    error = error or parent_error
                if check.message_id and not error:
                    author, error = reader.message_author(
                        guild_id, channel.id, check.message_id, refresh
                    )
                    owned = (
                        author == bundle.member.user_id
                        if author and bundle.member
                        else None
                    )
                    dependencies.add(
                        f"/channels/{channel.id}/messages/{check.message_id}"
                    )
            if check.scheduled_event_id and scope == "guild":
                creator, error = reader.scheduled_event_creator(
                    guild_id, check.scheduled_event_id, refresh
                )
                creator_is_bot = (
                    creator == bundle.member.user_id
                    if creator and bundle.member
                    else None
                )
                dependencies.add(
                    f"/guilds/{guild_id}/scheduled-events/{check.scheduled_event_id}"
                )
        observation = bundle.observation
        retry_after = bundle.retry_after
        if reader and observation:
            observations = [observation] + [
                reader.observations[p] for p in dependencies if p in reader.observations
            ]
            observation = Observation(
                min(o.observed_at for o in observations),
                min(o.expires_at for o in observations),
            )
            retry_after = (
                max(
                    [retry_after or 0]
                    + [
                        reader.reads[p].retry_after or 0
                        for p in dependencies
                        if p in reader.reads
                    ]
                )
                or None
            )
        reason: ReasonCode | None = error
        if (
            check.destination_source == "posted"
            and scope == "channel"
            and not check.channel_id
        ):
            reason = "malformed_snapshot"
        if guild_id is None and scope in ("channel", "guild"):
            reason = "no_server_configured"
        destination = Destination(
            kind="thread"
            if channel and channel.type in (10, 11, 12)
            else "channel"
            if scope == "channel"
            else "none",
            channel_id=check.channel_id if scope == "channel" else None,
            parent_id=channel.parent_id if channel else None,
            name=channel.name if channel else None,
            channel_type=channel.type if channel else None,
            source=check.destination_source,
        )
        resolved = ResolvedCheck(
            key=check.key,
            action=check.action,
            destination=destination,
            channel=channel,
            parent=parent,
            role_ids=check.role_ids,
            include_rsvp=check.include_rsvp,
            reference_present=check.reference_present,
            message_owned=owned,
            event_creator_is_bot=creator_is_bot,
            reason_override=reason,
        )
        result = evaluate(
            resolved,
            replace(bundle, observation=observation, retry_after=retry_after),
            now or timezone.now(),
        )
        if reader:
            result.refresh_state = reader.refresh_state
        results.append(result)
    return PermissionChecksResponse(guild_id=guild_id, checks=results)
