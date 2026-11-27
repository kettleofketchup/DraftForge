from org.api_connections.limits import CURSOR_BYTES
from org.api_connections.types import ConnectionConfig, MappedPage, MappedRow
from org.mmr import OrgMmrError, validate_org_mmr


class MappingError(ValueError):
    def __init__(self, code: str = "invalid_envelope") -> None:
        self.code = code
        super().__init__(code)


class _Missing:
    pass


MISSING = _Missing()


def resolve_path(value: object, path: str) -> object:
    if path == "":
        return value
    current = value
    for segment in path.split("."):
        if isinstance(current, dict):
            if segment not in current:
                return MISSING
            current = current[segment]
        elif isinstance(current, list) and segment.isdigit():
            index = int(segment)
            if index >= len(current):
                return MISSING
            current = current[index]
        else:
            return MISSING
    return current


def _identifier(value: object) -> str | None:
    if type(value) is int and value > 0:
        return str(value)
    if type(value) is str and value.isascii() and value.isdigit() and int(value) > 0:
        return str(int(value))
    return None


def _row(raw: object, config: ConnectionConfig, *, page: int, index: int) -> MappedRow:
    mapping = config.mmr_pull_config.mapping
    if not isinstance(raw, dict):
        return MappedRow(page, index, None, None, "invalid_entry")
    raw_id = resolve_path(raw, mapping.player_id_path)
    if raw_id is MISSING or raw_id is None or raw_id == "":
        return MappedRow(page, index, None, None, "missing_identifier")
    if mapping.player_id_type == "discord_id" and type(raw_id) is str:
        player_id = raw_id.strip() or None
    else:
        player_id = _identifier(raw_id)
    if player_id is None or len(player_id) > 64:
        return MappedRow(page, index, None, None, "invalid_identifier")
    mmr = resolve_path(raw, mapping.mmr_path)
    if mmr is MISSING:
        return MappedRow(page, index, player_id, None, "missing_mmr")
    if mmr is not None and type(mmr) is not int:
        return MappedRow(page, index, player_id, None, "invalid_mmr")
    try:
        validate_org_mmr(config.game_type or 1, mmr)
    except OrgMmrError:
        return MappedRow(page, index, player_id, None, "invalid_mmr")
    return MappedRow(page, index, player_id, mmr)


def map_page(payload: object, config: ConnectionConfig, *, page: int) -> MappedPage:
    pull = config.mmr_pull_config
    items = resolve_path(payload, pull.mapping.list_path)
    if not isinstance(items, list):
        raise MappingError()
    if pull.mapping.list_path == "" and not isinstance(payload, list):
        raise MappingError()
    has_more = False
    if pull.pagination.has_more_path is not None:
        raw_more = resolve_path(payload, pull.pagination.has_more_path)
        if raw_more is MISSING or raw_more is None:
            has_more = False
        elif type(raw_more) is bool:
            has_more = raw_more
        else:
            raise MappingError()
    next_cursor: str | int | None = None
    if pull.pagination.kind == "cursor" and pull.pagination.next_cursor_path:
        raw_cursor = resolve_path(payload, pull.pagination.next_cursor_path)
        if raw_cursor is MISSING or raw_cursor is None or raw_cursor == "":
            next_cursor = None
        elif type(raw_cursor) in (str, int):
            if len(str(raw_cursor).encode()) > CURSOR_BYTES:
                raise MappingError("cursor_too_large")
            next_cursor = raw_cursor
        else:
            raise MappingError()
    return MappedPage(
        rows=tuple(
            _row(raw, config, page=page, index=index) for index, raw in enumerate(items)
        ),
        has_more=has_more,
        next_cursor=next_cursor,
    )
