from datetime import datetime
from typing import Literal

DiscordTimestampStyle = Literal["t", "T", "d", "D", "f", "F", "R"]


def discord_timestamp(dt: datetime, style: DiscordTimestampStyle = "F") -> str:
    return f"<t:{int(dt.timestamp())}:{style}>"
