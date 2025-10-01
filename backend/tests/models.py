import json
import random
from datetime import date
from functools import cache
from pathlib import Path
from typing import List, Optional

from django.db import transaction
from pydantic import BaseModel

from backend.app.models import PositionsModel


# TODO create fixed data to be repeatable & deterministic tests alongside random data
@cache
def get_user_data():
    # Fetch user data from the database or any other source

    JSON_FILE: Path = Path(__file__).parent.absolute() / "data" / "discord_users.json"
    if not JSON_FILE.exists():
        raise FileNotFoundError(f"JSON file not found: {JSON_FILE}")
    with JSON_FILE.open("r", encoding="utf-8") as f:
        user_data = json.load(f)
    return user_data


class TournamentModel(BaseModel):
    name: Optional[str]
    date_played: Optional[date]
    state: Optional[str]
    tournament_type: Optional[str]
    users: List[int]


class UserModel(BaseModel):
    discordId: str
    username: Optional[str]
    steamId: Optional[int]
    mmr: Optional[int]

    def create_user(self):
        from app.models import CustomUser, PositionsModel

        discordData = get_user_data()[self.discordId]
        user, created = CustomUser.objects.get_or_create(discordId=self.discordId)
        if not created:
            return user
        if not self.mmr:
            mmr = random.randint(200, 6000)

        positions = PositionsModel.objects.create()
        positions.carry = random.randint(0, 5)
        positions.mid = random.randint(0, 5)
        positions.offlane = random.randint(0, 5)
        positions.soft_support = random.randint(0, 5)
        positions.hard_support = random.randint(0, 5)

        with transaction.atomic():
            print("creating user", self.username)
            user.createFromDiscordData(discordData)
            user.mmr = mmr

            positions.save()
            if random.randint(0, 1):
                user.steamId = str(
                    random.randint(76561197960265728, 76561197960265728 + 1000000)
                )

            user.positions = positions
            user.save()

        return user
