"""Lobby passwords: one per event, stored, and snapshotted on each lobby.

Staff choose a password mode on a series or an event:

- `fixed`: staff type the password ahead of time;
- `random`: DraftForge generates one when the event is created (or when the
  mode switches to random), and staff can regenerate it.

Every lobby in every tournament of the event uses that password. The event's
password is copied onto its tournament; a standalone tournament gets a random
one when lobbies are enabled. Each GameLobby keeps the password it was created
with (`GameLobby.password`), so a retried create is byte-identical and a later
change only affects lobbies created afterwards.

This module only imports the standard library and Django, so models and
serializers in `app` and `events` can use it without an import cycle.
Callers must keep passwords out of logs, events, bracket data and public
serializers.
"""

from __future__ import annotations

import secrets

from django.core.exceptions import ValidationError
from django.db import models

# dota_lobby accepts up to 32 characters; empty means no password.
MAX_LENGTH = 32
GENERATED_LENGTH = 12
# Lowercase letters and digits without the easily confused i, l, o, 0 and 1.
ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


class PasswordMode(models.TextChoices):
    FIXED = "fixed", "Fixed"
    RANDOM = "random", "Random"


def generate_password() -> str:
    """A random password that is easy to read out and type."""
    return "".join(secrets.choice(ALPHABET) for _ in range(GENERATED_LENGTH))


def validate_password(value: str) -> str:
    """Return `value` if dota_lobby and players can use it, else raise.

    Rejects empty values, more than 32 characters, anything outside printable
    ASCII and leading or trailing spaces (easy to miss when typing it in Dota).
    """
    if not isinstance(value, str) or value == "":
        raise ValidationError("Enter a lobby password.", code="required")
    if len(value) > MAX_LENGTH:
        raise ValidationError(
            f"The lobby password can have at most {MAX_LENGTH} characters.",
            code="max_length",
        )
    if any(not (0x20 <= ord(ch) <= 0x7E) for ch in value):
        raise ValidationError(
            "Use only letters, digits, spaces and standard punctuation.",
            code="invalid_characters",
        )
    if value != value.strip():
        raise ValidationError(
            "The lobby password cannot start or end with a space.",
            code="surrounding_spaces",
        )
    return value
