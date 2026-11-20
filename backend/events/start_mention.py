"""Recipient selection and message chunking for the pre-start member mention."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from events.constants import SEAT_HOLDING_STATUSES, Commitment, StartMentionScope
from events.schemas import EventSignupSchema

MAX_MENTIONS_PER_MESSAGE = 80
MAX_CONTENT_CHARS = 2000
INACTIVE_STATUSES: frozenset[str] = frozenset({"cancelled", "rejected", "dropped"})


@dataclass(frozen=True)
class StartMentionRecipients:
    discord_ids: list[str]
    skipped_no_discord_id: int


@dataclass(frozen=True)
class MentionChunk:
    content: str
    user_ids: list[str]


def _in_scope(signup: EventSignupSchema, scope: str) -> bool:
    if scope == StartMentionScope.MAIN:
        holds_seat = (
            signup.holds_seat
            if signup.holds_seat is not None
            else signup.status in SEAT_HOLDING_STATUSES
        )
        return holds_seat and signup.commitment != Commitment.MAYBE
    return signup.status not in INACTIVE_STATUSES


def start_mention_recipients(
    signups: Iterable[EventSignupSchema], scope: str
) -> StartMentionRecipients:
    """Discord IDs of in-scope members, once each, in signup order."""
    seen: set[str] = set()
    ids: list[str] = []
    skipped = 0
    for signup in signups:
        if not _in_scope(signup, scope):
            continue
        discord_id = signup.user_data.discordId if signup.user_data else None
        if not discord_id:
            skipped += 1
            continue
        if discord_id in seen:
            continue
        seen.add(discord_id)
        ids.append(discord_id)
    return StartMentionRecipients(discord_ids=ids, skipped_no_discord_id=skipped)


def chunk_mentions(
    discord_ids: Sequence[str],
    header: str,
    *,
    max_mentions: int = MAX_MENTIONS_PER_MESSAGE,
    max_chars: int = MAX_CONTENT_CHARS,
) -> list[MentionChunk]:
    """Split mentions into messages; the first carries the header."""
    chunks: list[MentionChunk] = []
    prefix = f"{header}\n" if header else ""
    current: list[str] = []
    length = len(prefix)
    for discord_id in discord_ids:
        mention = f"<@{discord_id}>"
        added = len(mention) + (1 if current else 0)
        if current and (len(current) >= max_mentions or length + added > max_chars):
            chunks.append(_chunk(prefix, current))
            prefix = ""
            current = []
            length = 0
            added = len(mention)
        current.append(discord_id)
        length += added
    if current:
        chunks.append(_chunk(prefix, current))
    return chunks


def _chunk(prefix: str, ids: list[str]) -> MentionChunk:
    content = prefix + " ".join(f"<@{i}>" for i in ids)
    return MentionChunk(content=content, user_ids=list(ids))
