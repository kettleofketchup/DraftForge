import json
import math
import re
from urllib.parse import unquote, urlsplit

from pydantic import ValidationError

from common.game import GameType
from org.api_connections.crypto import CredentialError, canonical_origin
from org.api_connections.limits import (
    CONFIG_BYTES,
    PATH_LENGTH,
    PATH_SEGMENTS,
    TEMPLATE_LEAVES,
)
from org.api_connections.types import (
    ConnectionConfig,
    CredentialField,
    MmrPullConfig,
    MmrPushConfig,
)


class ConnectionConfigError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


PLACEHOLDERS = frozenset(
    {
        "{{org.id}}",
        "{{game_type}}",
        "{{players.steam_account_ids}}",
        "{{players.steam64_ids}}",
        "{{players.discord_ids}}",
        "{{player.steam_account_id}}",
        "{{player.steam64}}",
        "{{player.discord_id}}",
        "{{page}}",
        "{{cursor}}",
        "{{page_size}}",
    }
)
SENSITIVE_KEYS = frozenset(
    {
        "apikey",
        "key",
        "token",
        "accesstoken",
        "secret",
        "password",
        "auth",
        "authorization",
        "signature",
        "sig",
    }
)


def _invalid() -> None:
    raise ConnectionConfigError("invalid_config")


def _check_json(value: object, *, depth: int = 0) -> None:
    if depth > 16:
        raise ConnectionConfigError("config_too_large")
    if type(value) is dict:
        for key, child in value.items():
            if type(key) is not str:
                _invalid()
            _check_json(child, depth=depth + 1)
    elif type(value) is list:
        for child in value:
            _check_json(child, depth=depth + 1)
    elif type(value) not in (str, int, float, bool, type(None)) or (
        type(value) is float and not math.isfinite(value)
    ):
        _invalid()


def _check_path(path: str, *, empty: bool = False) -> None:
    if empty and path == "":
        return
    segments = path.split(".")
    if (
        len(path) > PATH_LENGTH
        or len(segments) > PATH_SEGMENTS
        or any(
            not re.fullmatch(r"(?:[A-Za-z_][A-Za-z0-9_-]*|[0-9]+)", part)
            for part in segments
        )
    ):
        _invalid()


def _check_request_path(path: str) -> None:
    if len(path) > 2048 or not path.startswith("/") or path.startswith("//"):
        _invalid()
    structural = path.replace("{org_id}", "1").replace("{game_type}", "1")
    decoded = unquote(structural)
    if (
        any(c in decoded for c in "{}\\?#")
        or any(ord(c) <= 32 or ord(c) == 127 for c in decoded)
        or decoded.startswith("//")
        or any(part in (".", "..") for part in decoded.split("/"))
    ):
        _invalid()


def _leaves(value: object, *, designated: bool = False) -> int:
    if isinstance(value, dict):
        count = 0
        for key, child in value.items():
            sensitive = re.sub(r"[-_]", "", key).lower() in SENSITIVE_KEYS
            if sensitive and child != "{{credential}}":
                raise ConnectionConfigError("secret_like_literal")
            if "{" in key or "}" in key:
                _invalid()
            count += _leaves(child)
        return count
    if isinstance(value, list):
        return sum(_leaves(child) for child in value)
    if isinstance(value, str):
        if value == "{{credential}}":
            if not designated:
                _invalid()
        elif "{{" in value or "}}" in value:
            if value not in PLACEHOLDERS:
                _invalid()
    return 1


def _request_leaves(request: MmrPullConfig | MmrPushConfig, auth: str) -> int:
    _check_request_path(request.path)
    field: CredentialField | None = request.credential_field
    if field is not None and auth != "api_key_field":
        _invalid()
    if (
        isinstance(request, MmrPullConfig)
        and request.method == "GET"
        and request.body is not None
    ):
        _invalid()
    count = 0
    for location, values in (
        ("query", request.query),
        ("body", request.body),
    ):
        if values is None:
            if field and field.location == location:
                _invalid()
            continue
        for key, child in values.items():
            designated = (
                field is not None and field.location == location and field.key == key
            )
            if location == "query" and isinstance(child, (list, dict)):
                _invalid()
            if designated and child != "{{credential}}":
                _invalid()
            if (
                re.sub(r"[-_]", "", key).lower() in SENSITIVE_KEYS
                and child != "{{credential}}"
            ):
                raise ConnectionConfigError("secret_like_literal")
            if "{" in key or "}" in key or len(key) > 128:
                _invalid()
            count += _leaves(child, designated=designated)
        if field and field.location == location and field.key not in values:
            _invalid()
    if isinstance(request, MmrPushConfig) and request.body is not None:
        if not field or field.location != "body" or set(request.body) != {field.key}:
            _invalid()
    return count


def validate_connection_config(raw: dict[str, object]) -> ConnectionConfig:
    try:
        _check_json(raw)
        if type(raw) is not dict:
            _invalid()
        if (
            len(json.dumps(raw, ensure_ascii=False, allow_nan=False).encode())
            > CONFIG_BYTES
        ):
            raise ConnectionConfigError("config_too_large")
        config = ConnectionConfig.model_validate(raw)
        if not config.name.strip():
            _invalid()
        if config.game_type is not None and config.game_type not in GameType.values:
            _invalid()
        if config.outbound_base_url:
            canonical_origin(config.outbound_base_url)
            if (
                urlsplit(config.outbound_base_url).query
                or "{" in config.outbound_base_url
                or "}" in config.outbound_base_url
            ):
                _invalid()
        elif (
            config.outbound_auth != "none"
            or config.mmr_push_enabled
            or config.mmr_pull_enabled
            or config.promotion_push_enabled
        ):
            _invalid()
        count = _request_leaves(config.mmr_push_config, config.outbound_auth)
        count += _request_leaves(config.mmr_pull_config, config.outbound_auth)
        if count > TEMPLATE_LEAVES:
            raise ConnectionConfigError("config_too_large")
        pull = config.mmr_pull_config
        for path in (pull.mapping.list_path,):
            _check_path(path, empty=True)
        for path in (pull.mapping.player_id_path, pull.mapping.mmr_path):
            _check_path(path)
        for path in (pull.pagination.has_more_path, pull.pagination.next_cursor_path):
            if path is not None:
                _check_path(path)
        if (
            pull.pagination.kind == "cursor"
            and pull.pagination.next_cursor_path is None
        ):
            _invalid()
        if config.outbound_auth == "api_key_field":
            if (
                config.mmr_pull_enabled or pull != MmrPullConfig()
            ) and pull.credential_field is None:
                _invalid()
            if (
                config.mmr_push_enabled
                and config.mmr_push_config.credential_field is None
            ):
                _invalid()
        return config.model_copy(
            update={
                "name": config.name.strip(),
                "operations": sorted(set(config.operations)),
            }
        )
    except ConnectionConfigError:
        raise
    except (
        ValidationError,
        CredentialError,
        ValueError,
        TypeError,
        OverflowError,
        RecursionError,
    ):
        raise ConnectionConfigError("invalid_config") from None
