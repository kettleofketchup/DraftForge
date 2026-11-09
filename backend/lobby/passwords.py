"""Lobby passwords, derived on demand and never stored.

The password is an HMAC of the lobby's external_ref (`game:<pk>`) under one
of Django's secret keys, so:

- every create request for a game sends the same password, including a
  retried create and a new GameLobby row made after an ambiguous failure.
  dota_lobby then treats a repeat as a replay (200) of the lobby that may
  already exist, not as a conflict (409);
- nothing at rest needs encrypting.

Rotating DJANGO_SECRET_KEY must not change the password of a lobby that
already exists. Each GameLobby row records which key it was made under
(`password_key_id`, a fingerprint that reveals nothing about the key), and
the password is derived with whichever of SECRET_KEY and
SECRET_KEY_FALLBACKS matches. A new row for a game reuses the key of the
game's previous row while that key is still configured. Once the old key is
dropped from SECRET_KEY_FALLBACKS, derive_password raises
PasswordKeyUnavailable; read the live password from dota_lobby
(`get_lobby`) instead. Anything shown to players should come from dota_lobby
anyway, since that is the lobby they join.

The password is refused under the public development SECRET_KEY outside
DEBUG and tests: anyone could compute it.

Only the Django process can derive it: Celery workers run with a placeholder
SECRET_KEY and receive the password from the internal API instead. Callers
must keep it out of logs, events and bracket data.
"""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.crypto import salted_hmac

if TYPE_CHECKING:
    from lobby.models import GameLobby

PASSWORD_LENGTH = 12
_SALT = "draftforge.lobby.password"
_KEY_ID_SALT = "draftforge.lobby.password.key-id"
KEY_ID_LENGTH = 16


class PasswordKeyUnavailable(ValueError):
    """The secret key this lobby's password was made under is gone."""


def key_id(secret: str) -> str:
    """A fingerprint naming a secret key without revealing it."""
    return salted_hmac(_KEY_ID_SALT, "", secret=secret, algorithm="sha256").hexdigest()[
        :KEY_ID_LENGTH
    ]


def _configured_keys() -> list[str]:
    return [settings.SECRET_KEY, *getattr(settings, "SECRET_KEY_FALLBACKS", [])]


def current_key_id() -> str:
    return key_id(settings.SECRET_KEY)


def is_key_available(wanted: str) -> bool:
    return any(key_id(secret) == wanted for secret in _configured_keys())


def _key_for(game_lobby: GameLobby) -> str:
    for secret in _configured_keys():
        if key_id(secret) == game_lobby.password_key_id:
            return secret
    raise PasswordKeyUnavailable(
        "the secret key this lobby's password was derived with is no longer in "
        "SECRET_KEY or SECRET_KEY_FALLBACKS"
    )


def _insecure_key_allowed() -> bool:
    return bool(
        settings.DEBUG
        or getattr(settings, "TEST", False)
        or getattr(settings, "RUNNING_TESTS", False)
    )


def derive_password(game_lobby: GameLobby) -> str:
    """A 12-character lowercase [a-z2-7] password for this lobby's game."""
    if game_lobby.pk is None or not game_lobby.password_key_id:
        raise ValueError("save the GameLobby before deriving its password")
    secret = _key_for(game_lobby)
    insecure = getattr(settings, "INSECURE_DEV_SECRET_KEY", None)
    if secret == insecure and not _insecure_key_allowed():
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY is not set: lobby passwords would be derived "
            "from the public development key"
        )
    digest = salted_hmac(
        _SALT, game_lobby.external_ref, secret=secret, algorithm="sha256"
    ).digest()
    return base64.b32encode(digest).decode("ascii")[:PASSWORD_LENGTH].lower()
