"""Lobby passwords, derived on demand and never stored.

The password is an HMAC of the lobby's ref and row ID under Django's
SECRET_KEY, so:

- a retried create sends exactly the same request, which dota_lobby treats as
  a repeat (200) rather than a conflict (409);
- nothing at rest needs encrypting;
- a new GameLobby row (a recreated lobby) gets a new password.

Only the Django process can derive it: Celery workers run with a placeholder
SECRET_KEY and receive the password from the internal API instead. Callers
must keep it out of logs, events and bracket data.
"""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING

from django.utils.crypto import salted_hmac

if TYPE_CHECKING:
    from lobby.models import GameLobby

PASSWORD_LENGTH = 12
_SALT = "draftforge.lobby.password"


def derive_password(game_lobby: GameLobby) -> str:
    """A 12-character lowercase [a-z2-7] password for this lobby row."""
    if game_lobby.pk is None:
        raise ValueError("save the GameLobby before deriving its password")
    digest = salted_hmac(
        _SALT,
        f"{game_lobby.external_ref}:{game_lobby.pk}",
        algorithm="sha256",
    ).digest()
    return base64.b32encode(digest).decode("ascii")[:PASSWORD_LENGTH].lower()
