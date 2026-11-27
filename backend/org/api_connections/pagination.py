import hashlib
import json
from dataclasses import dataclass, field

from org.api_connections.types import ConnectionConfig, MappedPage


class PaginationError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class Position:
    page: int
    cursor: str | int | None = None
    seen: list[str | int] = field(default_factory=list)


def first_page(config: ConnectionConfig) -> int | None:
    pagination = config.mmr_pull_config.pagination
    return pagination.start if pagination.kind == "page" else None


def _digest(mapped: MappedPage) -> str:
    rows = [(row.player_id, row.mmr, row.error) for row in mapped.rows]
    return "sha256:" + hashlib.sha256(json.dumps(rows).encode()).hexdigest()


def next_position(
    config: ConnectionConfig,
    mapped: MappedPage,
    *,
    page: int,
    seen: list[str | int],
) -> Position | None:
    pagination = config.mmr_pull_config.pagination
    if pagination.kind == "none":
        return None
    if pagination.kind == "cursor":
        cursor = mapped.next_cursor
        if cursor is None:
            return None
        if any(type(item) is type(cursor) and item == cursor for item in seen):
            raise PaginationError("pagination_loop")
        return Position(page=page + 1, cursor=cursor, seen=[*seen, cursor])
    if not mapped.rows:
        return None
    digest = _digest(mapped)
    if digest in seen:
        raise PaginationError("pagination_loop")
    if pagination.has_more_path is not None:
        more = mapped.has_more
    else:
        more = len(mapped.rows) >= pagination.page_size
    if not more:
        return None
    return Position(page=page + 1, seen=[*seen, digest])
