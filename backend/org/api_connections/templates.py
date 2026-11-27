from typing import Literal

from pydantic import JsonValue

from app.models import CustomUser
from org.api_connections.crypto import canonical_origin
from org.api_connections.types import (
    ConnectionConfig,
    MemberSnapshot,
    SafeHttpRequest,
    SnapshotMember,
)

IdentifierKind = Literal["steam_account_id", "steam64", "discord_id"]

ARRAY_PLACEHOLDERS: dict[str, IdentifierKind] = {
    "{{players.steam_account_ids}}": "steam_account_id",
    "{{players.steam64_ids}}": "steam64",
    "{{players.discord_ids}}": "discord_id",
}
MEMBER_PLACEHOLDERS: dict[str, IdentifierKind] = {
    "{{player.steam_account_id}}": "steam_account_id",
    "{{player.steam64}}": "steam64",
    "{{player.discord_id}}": "discord_id",
}


class TemplateError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class _Omit:
    pass


OMIT = _Omit()


def member_identifier(member: SnapshotMember, kind: IdentifierKind) -> str | None:
    if kind == "discord_id":
        return member.discord_id or None
    if member.steam_account_id is None:
        return None
    if kind == "steam64":
        return str(member.steam_account_id + CustomUser.STEAM_ID_64_BASE)
    return str(member.steam_account_id)


def _leaves(value: object) -> list[str]:
    if isinstance(value, dict):
        return [leaf for child in value.values() for leaf in _leaves(child)]
    if isinstance(value, list):
        return [leaf for child in value for leaf in _leaves(child)]
    return [value] if isinstance(value, str) else []


def identifier_kinds(config: ConnectionConfig) -> set[IdentifierKind]:
    pull = config.mmr_pull_config
    leaves = _leaves(pull.query) + _leaves(pull.body or {})
    return {
        kind
        for leaf in leaves
        if (kind := ARRAY_PLACEHOLDERS.get(leaf) or MEMBER_PLACEHOLDERS.get(leaf))
    }


class _Renderer:
    def __init__(
        self,
        config: ConnectionConfig,
        snapshot: MemberSnapshot,
        page: int | None,
        cursor: str | int | None,
    ) -> None:
        self.config = config
        self.snapshot = snapshot
        self.page = page
        self.cursor = cursor

    def scalar(self, value: str, *, query: bool) -> JsonValue | _Omit:
        if value == "{{org.id}}":
            return self.snapshot.organization_id
        if value == "{{game_type}}":
            return self.snapshot.game_type
        if value == "{{page_size}}":
            return self.config.mmr_pull_config.pagination.page_size
        if value == "{{page}}":
            if self.page is None:
                raise TemplateError("invalid_config")
            return self.page
        if value == "{{cursor}}":
            return OMIT if self.cursor is None else self.cursor
        if value in ARRAY_PLACEHOLDERS:
            ids = [
                identifier
                for member in self.snapshot.members
                if (identifier := member_identifier(member, ARRAY_PLACEHOLDERS[value]))
            ]
            return ",".join(ids) if query else ids
        if value in MEMBER_PLACEHOLDERS:
            if len(self.snapshot.members) != 1:
                raise TemplateError("invalid_config")
            identifier = member_identifier(
                self.snapshot.members[0], MEMBER_PLACEHOLDERS[value]
            )
            if identifier is None:
                raise TemplateError("missing_identifier")
            return identifier
        if "{{" in value or "}}" in value:
            raise TemplateError("invalid_config")
        return value

    def render(self, value: JsonValue, *, query: bool) -> JsonValue | _Omit:
        if isinstance(value, dict):
            rendered = {
                key: self.render(child, query=query) for key, child in value.items()
            }
            return {k: v for k, v in rendered.items() if not isinstance(v, _Omit)}
        if isinstance(value, list):
            items = [self.render(child, query=query) for child in value]
            return [item for item in items if not isinstance(item, _Omit)]
        if isinstance(value, str):
            return self.scalar(value, query=query)
        return value


def render_request(
    config: ConnectionConfig,
    snapshot: MemberSnapshot,
    *,
    page: int | None,
    cursor: str | int | None,
    credential: str | None,
) -> SafeHttpRequest:
    pull = config.mmr_pull_config
    if not config.outbound_base_url:
        raise TemplateError("invalid_config")
    field = pull.credential_field
    query = dict(pull.query)
    body = dict(pull.body) if pull.body is not None else None
    if field is not None:
        (query if field.location == "query" else body or {}).pop(field.key, None)
    renderer = _Renderer(config, snapshot, page, cursor)
    rendered_query = renderer.render(query, query=True)
    rendered_body = (
        renderer.render(body, query=False)
        if body is not None and pull.method == "POST"
        else None
    )
    if config.outbound_auth != "none" and not credential:
        raise TemplateError("credential_unavailable")
    path = pull.path.replace("{org_id}", str(snapshot.organization_id)).replace(
        "{game_type}", str(snapshot.game_type)
    )
    return SafeHttpRequest(
        url=config.outbound_base_url.rstrip("/") + path,
        method=pull.method,
        query=rendered_query,
        body=rendered_body,
        auth=config.outbound_auth,
        credential=credential if config.outbound_auth != "none" else None,
        credential_origin=(
            canonical_origin(config.outbound_base_url)
            if config.outbound_auth != "none"
            else None
        ),
        credential_field=field if config.outbound_auth == "api_key_field" else None,
    )
