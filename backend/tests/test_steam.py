# tests/test_steam.py
"""
Test endpoints for creating Steam match data for Cypress tests.
"""
import logging
import random

from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from app.models import Game, Tournament
from common.utils import isTestEnvironment
from steam.models import Match, PlayerMatchStats

log = logging.getLogger(__name__)

# Dota 2 hero IDs for test data (common heroes)
TEST_HERO_IDS = [
    1,  # Anti-Mage
    2,  # Axe
    5,  # Crystal Maiden
    6,  # Drow Ranger
    8,  # Juggernaut
    11,  # Shadow Fiend
    14,  # Pudge
    22,  # Zeus
    25,  # Lina
    26,  # Lion
    27,  # Shadow Shaman
    30,  # Witch Doctor
    35,  # Sniper
    41,  # Faceless Void
    44,  # Phantom Assassin
    47,  # Viper
    74,  # Invoker
    86,  # Rubick
    90,  # Keeper of the Light
    102,  # Abaddon
]


def create_match_with_stats(match_id: int, game: Game = None) -> Match:
    """
    Create a Steam Match with 10 PlayerMatchStats records (5 per team).
    If game is provided, links the match to that game.
    """
    # Create the match
    match, created = Match.objects.get_or_create(
        match_id=match_id,
        defaults={
            "radiant_win": random.choice([True, False]),
            "duration": random.randint(1200, 3600),  # 20-60 minutes
            "start_time": 1704067200,  # 2024-01-01 00:00:00
            "game_mode": 22,  # All Pick
            "lobby_type": 7,  # Ranked
            "league_id": None,
        },
    )

    if not created:
        # Match already exists, just return it
        return match

    # Get 10 random hero IDs
    heroes = random.sample(TEST_HERO_IDS, 10)

    # Create player stats for Radiant (slots 0-4) and Dire (slots 128-132)
    radiant_slots = [0, 1, 2, 3, 4]
    dire_slots = [128, 129, 130, 131, 132]

    for i, (slot, hero_id) in enumerate(zip(radiant_slots + dire_slots, heroes)):
        PlayerMatchStats.objects.create(
            match=match,
            steam_id=76561198000000000 + i,  # Fake Steam IDs
            player_slot=slot,
            hero_id=hero_id,
            kills=random.randint(0, 20),
            deaths=random.randint(0, 15),
            assists=random.randint(0, 25),
            gold_per_min=random.randint(200, 800),
            xp_per_min=random.randint(200, 700),
            last_hits=random.randint(50, 400),
            denies=random.randint(0, 50),
            hero_damage=random.randint(5000, 50000),
            tower_damage=random.randint(0, 10000),
            hero_healing=random.randint(0, 20000),
        )

    # Link to game if provided
    if game:
        game.gameid = match_id
        game.save()

    return match


@api_view(["POST"])
@permission_classes([AllowAny])
def create_test_match(request):
    """
    Create a test Steam match with player stats.

    POST body (all optional):
    - match_id: int (default: random)
    - tournament_id: int (if provided, links to first game in tournament)
    - game_id: int (if provided, links to specific game)
    """
    if not isTestEnvironment(request):
        return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)

    match_id = request.data.get("match_id", random.randint(8000000000, 9000000000))
    tournament_id = request.data.get("tournament_id")
    game_id = request.data.get("game_id")

    game = None

    # Try to find a game to link the match to
    if game_id:
        try:
            game = Game.objects.get(pk=game_id)
        except Game.DoesNotExist:
            return Response(
                {"detail": f"Game {game_id} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
    elif tournament_id:
        try:
            tournament = Tournament.objects.get(pk=tournament_id)
            # Get first game in tournament that doesn't have a gameid
            game = tournament.games.filter(gameid__isnull=True).first()
            if not game:
                # Or just get any game
                game = tournament.games.first()
        except Tournament.DoesNotExist:
            return Response(
                {"detail": f"Tournament {tournament_id} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

    with transaction.atomic():
        match = create_match_with_stats(match_id, game)

    return Response(
        {
            "match_id": match.match_id,
            "radiant_win": match.radiant_win,
            "duration": match.duration,
            "game_id": game.pk if game else None,
            "tournament_id": game.tournament_id if game else None,
            "player_count": match.players.count(),
        }
    )
