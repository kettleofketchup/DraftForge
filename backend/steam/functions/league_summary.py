from fractions import Fraction
from typing import Literal, TypedDict

from steam.functions.stats_update import player_won
from steam.models import PlayerMatchStats
from telemetry.logging import get_logger

logger = get_logger(__name__)

BUCKET_SIZE = 10
BUCKET_COUNT = 10
RECENT_LIMIT = 10

Result = Literal["W", "L"]


class Streak(TypedDict):
    result: Result
    count: int


class PlayerSummary(TypedDict):
    rank: int | None
    top_percent: int | None
    games: int
    wins: int
    losses: int
    win_rate: float
    bucket: int | None
    recent: list[Result]
    streak: Streak | None


class Bucket(TypedDict):
    min: int
    max: int
    count: int


class Distribution(TypedDict):
    bucket_size: int
    buckets: list[Bucket]


class LeagueSummary(TypedDict):
    min_games: int
    population: int
    players: dict[str, PlayerSummary]
    distribution: Distribution


def top_percent(rank: int, population: int) -> int:
    return (rank * 100 + population - 1) // population


def _empty_buckets() -> list[Bucket]:
    return [
        {"min": i * BUCKET_SIZE, "max": (i + 1) * BUCKET_SIZE, "count": 0}
        for i in range(BUCKET_COUNT)
    ]


def empty_league_summary(min_games: int) -> LeagueSummary:
    return {
        "min_games": min_games,
        "population": 0,
        "players": {},
        "distribution": {"bucket_size": BUCKET_SIZE, "buckets": _empty_buckets()},
    }


def _resolve(rows: list[tuple[int, int | None, bool]]) -> bool | None:
    results = {won for _, _, won in rows}
    if len(results) == 1:
        return results.pop()
    owned = [won for steam_id, user_steamid, won in rows if steam_id == user_steamid]
    return owned[0] if len(owned) == 1 else None


def _results_by_user(steam_league_id: int) -> dict[int, list[Result]]:
    rows = (
        PlayerMatchStats.objects.nocache()
        .filter(match__league_id=steam_league_id, user__isnull=False)
        .values_list(
            "user_id",
            "steam_id",
            "user__steamid",
            "player_slot",
            "match__radiant_win",
            "match__start_time",
            "match_id",
        )
        .order_by("match__start_time", "match_id")
    )
    grouped: dict[tuple[int, int], list[tuple[int, int | None, bool]]] = {}
    for user_id, steam_id, user_steamid, slot, radiant_win, _, match_id in rows:
        grouped.setdefault((user_id, match_id), []).append(
            (steam_id, user_steamid, player_won(slot, radiant_win))
        )

    results: dict[int, list[Result]] = {}
    for (user_id, _), match_rows in grouped.items():
        won = _resolve(match_rows)
        if won is not None:
            results.setdefault(user_id, []).append("W" if won else "L")
    return results


def _streak(results: list[Result]) -> Streak:
    last = results[-1]
    count = 0
    for result in reversed(results):
        if result != last:
            break
        count += 1
    return {"result": last, "count": count}


def compute_league_summary(steam_league_id: int, min_games: int) -> LeagueSummary:
    summary = empty_league_summary(min_games)
    players = summary["players"]
    buckets = summary["distribution"]["buckets"]

    for user_id, results in _results_by_user(steam_league_id).items():
        games = len(results)
        wins = results.count("W")
        players[str(user_id)] = {
            "rank": None,
            "top_percent": None,
            "games": games,
            "wins": wins,
            "losses": games - wins,
            "win_rate": round(wins / games, 4),
            "bucket": None,
            "recent": results[-RECENT_LIMIT:],
            "streak": _streak(results),
        }

    ranked = sorted(
        (p for p in players.values() if p["games"] >= min_games),
        key=lambda p: (-Fraction(p["wins"], p["games"]), -p["games"], -p["wins"]),
    )
    population = len(ranked)
    previous: tuple[Fraction, int] | None = None
    rank = 0
    for position, player in enumerate(ranked, start=1):
        key = (Fraction(player["wins"], player["games"]), player["games"])
        if key != previous:
            rank = position
            previous = key
        bucket = min(player["wins"] * BUCKET_COUNT // player["games"], BUCKET_COUNT - 1)
        player["rank"] = rank
        player["top_percent"] = top_percent(rank, population)
        player["bucket"] = bucket
        buckets[bucket]["count"] += 1
    summary["population"] = population

    logger.debug(
        "league_summary_computed",
        system="steam",
        subsystem="stats",
        steam_league_id=steam_league_id,
        min_games=min_games,
        population=population,
        players=len(players),
    )
    return summary
