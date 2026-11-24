"""Wire contract for connecting an organization to its Discord server.

Django-free so ``export_install_schema.py`` runs under ``python -I``.
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class Response(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class DiscordConnectError(StrEnum):
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    FORBIDDEN = "forbidden"
    INVALID_SERVER = "invalid_server"
    BOT_MISSING = "bot_missing"


class DiscordInstallLink(Response):
    url: str


class DiscordBotStatus(Response):
    has_bot: bool
    reason: Literal["no_server_configured"] | None = None
    guild_name: str | None = None


class DiscordConnectApi(BaseModel):
    install_link: DiscordInstallLink
    bot_status: DiscordBotStatus
    connect_error: DiscordConnectError
