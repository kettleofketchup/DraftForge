"""Components V2 payload for one part of a leadership review DM (spec §7.2)."""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Literal

from discordbot.custom_ids import LEADERSHIP_REVIEW_PREFIX
from discordbot.dm import V2_FLAG

MAX_TRAITS_PER_MESSAGE: Final[int] = 5
MAX_COMPONENTS: Final[int] = 40
SCORES: Final[tuple[int, ...]] = (1, 2, 3, 4, 5)
NAME_MAX: Final[int] = 100

ACTION_ROW: Final[int] = 1
BUTTON: Final[int] = 2
TEXT_DISPLAY: Final[int] = 10
PRIMARY: Final[int] = 1
SECONDARY: Final[int] = 2
LINK: Final[int] = 5

SAVES_LINE: Final[str] = "Your review saves once both messages are complete."
TRAITS_CHANGED_LINE: Final[str] = "Traits changed. Finish on the site."
CLOSED_LINE: Final[str] = "Reviews for this event are closed for now."

StatusState = Literal["progress", "saved", "traits_changed", "closed"]

_MARKDOWN = re.compile(r"([\\*_~`|])")


@dataclass(frozen=True)
class TraitRow:
    trait_id: int
    label: str
    active: bool


def _escape(text: str) -> str:
    return _MARKDOWN.sub(r"\\\1", text[:NAME_MAX])


def _text(content: str) -> dict[str, Any]:
    return {"type": TEXT_DISPLAY, "content": content}


def _header(
    captain_name: str, event_name: str, close_at: datetime, part: int, parts: int
) -> str:
    when = f"Reviews close <t:{int(close_at.timestamp())}:R>"
    prefix = f"Part {part} of {parts} · " if parts > 1 else ""
    return (
        f"**Rate your captain: {_escape(captain_name)} ({_escape(event_name)})**\n"
        f"{prefix}{when}"
    )


def _trait_label(trait: TraitRow) -> str:
    label = f"**{_escape(trait.label)}**"
    return label if trait.active else f"{label} (no longer used)"


def _button_row(snapshot_id: int, trait_id: int, chosen: int | None) -> dict[str, Any]:
    return {
        "type": ACTION_ROW,
        "components": [
            {
                "type": BUTTON,
                "style": PRIMARY if score == chosen else SECONDARY,
                "label": str(score),
                "custom_id": f"{LEADERSHIP_REVIEW_PREFIX}{snapshot_id}:{trait_id}:{score}",
            }
            for score in SCORES
        ],
    }


def _status(
    state: StatusState,
    *,
    traits: Sequence[TraitRow],
    scores: Mapping[int, int],
    parts: int,
    close_at: datetime,
) -> str:
    if state == "saved":
        return (
            f"Review saved. You can change it until <t:{int(close_at.timestamp())}:f>."
        )
    if state == "traits_changed":
        return TRAITS_CHANGED_LINE
    if state == "closed":
        return CLOSED_LINE
    active = [t for t in traits if t.active]
    done = sum(1 for t in active if t.trait_id in scores)
    if parts == 1:
        return f"{done} of {len(active)} scored"
    return f"{done} of {len(active)} scored in this message\n{SAVES_LINE}"


def render_part(
    *,
    captain_name: str,
    event_name: str,
    close_at: datetime,
    part: int,
    parts: int,
    traits: Sequence[TraitRow],
    scores: Mapping[int, int],
    snapshot_id: int,
    site_url: str,
    state: StatusState,
) -> dict[str, Any]:
    if not 0 < len(traits) <= MAX_TRAITS_PER_MESSAGE:
        raise ValueError(f"A review message holds 1-{MAX_TRAITS_PER_MESSAGE} traits.")
    components: list[dict[str, Any]] = [
        _text(_header(captain_name, event_name, close_at, part, parts))
    ]
    for trait in traits:
        components.append(_text(_trait_label(trait)))
        components.append(
            _button_row(snapshot_id, trait.trait_id, scores.get(trait.trait_id))
        )
    components.append(
        _text(
            _status(state, traits=traits, scores=scores, parts=parts, close_at=close_at)
        )
    )
    components.append(
        {
            "type": ACTION_ROW,
            "components": [
                {
                    "type": BUTTON,
                    "style": LINK,
                    "label": "Review on site",
                    "url": site_url,
                }
            ],
        }
    )
    payload = {"flags": V2_FLAG, "components": components}
    if count_components(payload) > MAX_COMPONENTS:
        raise ValueError("Review message exceeds the Discord component limit.")
    return payload


def _count(components: Sequence[Mapping[str, Any]]) -> int:
    return sum(1 + _count(c.get("components", ())) for c in components)


def count_components(payload: Mapping[str, Any]) -> int:
    return _count(payload.get("components", ()))
