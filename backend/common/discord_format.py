from datetime import datetime
from typing import Literal

from django.utils import timezone

DiscordTimestampStyle = Literal["t", "T", "d", "D", "f", "F", "R"]


def discord_timestamp(dt: datetime, style: DiscordTimestampStyle = "F") -> str:
    if timezone.is_naive(dt):
        raise ValueError("discord_timestamp needs an aware datetime")
    return f"<t:{int(dt.timestamp())}:{style}>"
