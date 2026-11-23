"""Readers for the production user fields shared by the prod sync commands."""

from typing import Any

from app.models import CustomUser, PositionsModel


def steam_account_id(user_data: dict[str, Any]) -> int | None:
    account_id = user_data.get("steam_account_id")
    if account_id is not None:
        return account_id
    steamid = user_data.get("steamid")
    return steamid - CustomUser.STEAM_ID_64_BASE if steamid else None


POSITION_FIELDS = ("carry", "mid", "offlane", "soft_support", "hard_support")


def position_values(user_data: dict[str, Any]) -> dict[str, int]:
    positions = user_data.get("positions") or {}
    return {field: positions.get(field, 0) for field in POSITION_FIELDS}


def create_positions(user_data: dict[str, Any]) -> PositionsModel:
    return PositionsModel.objects.create(**position_values(user_data))
