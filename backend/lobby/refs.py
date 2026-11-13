"""external_ref values: how DraftForge names its lobbies in dota_lobby.

A game's ref is `<DOTA_LOBBY_REF_PREFIX>:<game pk>`, for example `game:42`.
The prefix lets a staging and a production DraftForge share one dota_lobby:
each ignores refs with the other's prefix. dota_lobby lets a ref be reused
once its lobby has ended, so every lobby a game gets has the same ref.
"""

from __future__ import annotations

from config.dota_lobby import DotaLobbyConfig


def _prefix(prefix: str | None) -> str:
    return prefix if prefix is not None else DotaLobbyConfig.from_env().ref_prefix


def build_external_ref(game_pk: int, prefix: str | None = None) -> str:
    if game_pk <= 0:
        raise ValueError("game_pk must be positive")
    return f"{_prefix(prefix)}:{game_pk}"


def parse_external_ref(ref: str, prefix: str | None = None) -> int | None:
    """The game pk in `ref`, or None when the ref is not one of ours."""
    head, sep, tail = ref.rpartition(":")
    if not sep or head != _prefix(prefix):
        return None
    if not tail.isascii() or not tail.isdigit() or tail.startswith("0"):
        return None
    return int(tail)
