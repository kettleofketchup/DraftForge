from enum import StrEnum

from django.db import models


# Team draft pick-order styles
class DraftStyles(StrEnum):
    snake = "snake"
    normal = "normal"
    shuffle = "shuffle"


class GameMode(models.TextChoices):
    NORMAL = "normal", "Normal"
    CAPTAINS_MODE = "captains_mode", "Captain's Mode"
    TURBO = "turbo", "Turbo"
    CUSTOM = "custom", "Custom Lobby"


class DotaLobbyMode(models.TextChoices):
    """Whether DraftForge asks dota_lobby for in-game lobbies (lobby app)."""

    OFF = "off", "Off"
    MANUAL = "manual", "Manual"
    AUTO = "auto", "Automatic"


class DotaLobbyLaunch(models.TextChoices):
    """dota_lobby's `launch` request field: who starts the match."""

    MANUAL = "manual", "Manual"
    AUTO = "auto", "Automatic"


TOURNAMENT_TYPE_CHOICES = [
    ("single_elimination", "Single Elimination"),
    ("double_elimination", "Double Elimination"),
    ("swiss", "Swiss Bracket"),
]
