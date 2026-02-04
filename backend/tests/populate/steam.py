"""
Steam matches population module for test database.
Creates mock Steam matches and bracket games for tournaments.
"""

from django.db import models

from app.models import CustomUser, Game
from tests.data.tournaments import BRACKET_TEST_TOURNAMENTS

from .constants import DTX_STEAM_LEAGUE_ID
from .utils import flush_redis_cache


def populate_steam_matches(force=False):
    """
    Generate and save mock Steam matches for test tournaments.
    Creates bracket Game objects with different completion states:
    - Tournament 1 (Completed Bracket Test): All 6 games completed with Steam matches
    - Tournament 2 (Partial Bracket Test): 2 games completed, 4 pending
    - Tournament 3 (Pending Bracket Test): All games pending (no completed games)

    Args:
        force: If True, delete existing mock matches and games first
    """
    from app.models import Tournament
    from steam.mocks.mock_match_generator import generate_mock_matches_for_tournament
    from steam.models import Match, PlayerMatchStats

    print("Populating Steam matches and bracket games...")

    # Find tournaments by name from Pydantic configs
    tournament_names = [t.name for t in BRACKET_TEST_TOURNAMENTS]
    db_tournaments = {
        t.name: t for t in Tournament.objects.filter(name__in=tournament_names)
    }

    if len(db_tournaments) < len(BRACKET_TEST_TOURNAMENTS):
        missing = set(tournament_names) - set(db_tournaments.keys())
        print(f"Missing tournaments: {missing}. Run populate_tournaments first.")
        return

    # Check for existing mock matches (IDs starting with 9000000000)
    existing_matches = Match.objects.filter(
        match_id__gte=9000000000, match_id__lt=9100000000
    )
    existing_games = Game.objects.filter(tournament__in=db_tournaments.values())

    if existing_matches.exists() or existing_games.exists():
        if force:
            print(f"Deleting {existing_matches.count()} existing mock matches")
            print(f"Deleting {existing_games.count()} existing games")
            existing_matches.delete()
            existing_games.delete()
        else:
            print(f"Mock data already exists. Use force=True to regenerate.")
            return

    # Define bracket structure for 4-team double elimination
    bracket_structure = [
        {
            "round": 1,
            "bracket_type": "winners",
            "position": 0,
        },  # Match 0: Winners R1 M1
        {
            "round": 1,
            "bracket_type": "winners",
            "position": 1,
        },  # Match 1: Winners R1 M2
        {"round": 1, "bracket_type": "losers", "position": 0},  # Match 2: Losers R1
        {
            "round": 2,
            "bracket_type": "winners",
            "position": 0,
        },  # Match 3: Winners Final
        {"round": 2, "bracket_type": "losers", "position": 0},  # Match 4: Losers Final
        {
            "round": 1,
            "bracket_type": "grand_finals",
            "position": 0,
        },  # Match 5: Grand Final
    ]

    # Use tournament configs from Pydantic models
    for tournament_config in BRACKET_TEST_TOURNAMENTS:
        tournament = db_tournaments[tournament_config.name]
        completed_count = tournament_config.completed_game_count or 0
        match_id_base = tournament_config.match_id_base or 9000000001

        teams = list(tournament.teams.all()[:4])
        if len(teams) < 4:
            print(
                f"Tournament '{tournament.name}' needs 4 teams, has {len(teams)}, skipping..."
            )
            continue

        # Generate mock matches only if we need completed games
        mock_matches = []
        if completed_count > 0:
            try:
                mock_matches = generate_mock_matches_for_tournament(tournament)
            except ValueError as e:
                print(f"Failed to generate matches for {tournament.name}: {e}")
                continue

        games = []
        match_results = []  # (radiant_team, dire_team, winner, loser)

        for idx, bracket_info in enumerate(bracket_structure):
            is_completed = idx < completed_count

            # Determine teams based on bracket position
            # Only assign teams to later rounds if their source games are COMPLETED
            if idx == 0:  # Winners R1 Match 1
                radiant_team, dire_team = teams[0], teams[1]
            elif idx == 1:  # Winners R1 Match 2
                radiant_team, dire_team = teams[2], teams[3]
            elif idx == 2:  # Losers R1 - needs games 0 and 1 completed
                if completed_count >= 2 and len(match_results) >= 2:
                    radiant_team = match_results[0][3]  # Loser of match 0
                    dire_team = match_results[1][3]  # Loser of match 1
                else:
                    radiant_team, dire_team = None, None
            elif idx == 3:  # Winners Final - needs games 0 and 1 completed
                if completed_count >= 2 and len(match_results) >= 2:
                    radiant_team = match_results[0][2]  # Winner of match 0
                    dire_team = match_results[1][2]  # Winner of match 1
                else:
                    radiant_team, dire_team = None, None
            elif idx == 4:  # Losers Final - needs games 2 and 3 completed
                if completed_count >= 4 and len(match_results) >= 4:
                    radiant_team = match_results[2][2]  # Winner of Losers R1
                    dire_team = match_results[3][3]  # Loser of Winners Final
                else:
                    radiant_team, dire_team = None, None
            elif idx == 5:  # Grand Final - needs games 3 and 4 completed
                if completed_count >= 5 and len(match_results) >= 5:
                    radiant_team = match_results[3][2]  # Winner of Winners Final
                    dire_team = match_results[4][2]  # Winner of Losers Final
                else:
                    radiant_team, dire_team = None, None

            # Handle completed games with Steam match data
            winner = None
            gameid = None

            if is_completed and idx < len(mock_matches):
                result = mock_matches[idx]["result"]
                gameid = match_id_base + idx
                radiant_win = result["radiant_win"]

                # Save Steam Match
                match, _ = Match.objects.update_or_create(
                    match_id=gameid,
                    defaults={
                        "radiant_win": radiant_win,
                        "duration": result["duration"],
                        "start_time": result["start_time"],
                        "game_mode": result["game_mode"],
                        "lobby_type": result["lobby_type"],
                        "league_id": DTX_STEAM_LEAGUE_ID,
                    },
                )

                # Save PlayerMatchStats
                for player_data in result["players"]:
                    steam_id = player_data["account_id"] + 76561197960265728
                    user = CustomUser.objects.filter(steamid=steam_id).first()

                    PlayerMatchStats.objects.update_or_create(
                        match=match,
                        steam_id=steam_id,
                        defaults={
                            "user": user,
                            "player_slot": player_data["player_slot"],
                            "hero_id": player_data["hero_id"],
                            "kills": player_data["kills"],
                            "deaths": player_data["deaths"],
                            "assists": player_data["assists"],
                            "gold_per_min": player_data["gold_per_min"],
                            "xp_per_min": player_data["xp_per_min"],
                            "last_hits": player_data["last_hits"],
                            "denies": player_data["denies"],
                            "hero_damage": player_data["hero_damage"],
                            "tower_damage": player_data["tower_damage"],
                            "hero_healing": player_data["hero_healing"],
                        },
                    )

                winner = radiant_team if radiant_win else dire_team
                loser = dire_team if radiant_win else radiant_team
                match_results.append((radiant_team, dire_team, winner, loser))
            # For pending games, no need to track placeholder results
            # Teams for later rounds will be determined when games are actually completed

            # Create Game object
            game = Game.objects.create(
                tournament=tournament,
                round=bracket_info["round"],
                bracket_type=bracket_info["bracket_type"],
                position=bracket_info["position"],
                elimination_type="double",  # All our test brackets are double elim
                radiant_team=radiant_team,
                dire_team=dire_team,
                winning_team=winner if is_completed else None,
                gameid=gameid,
                status="completed" if is_completed else "pending",
            )
            games.append(game)

        # Set up next_game links for bracket flow
        if len(games) >= 6:
            games[0].next_game = games[3]
            games[0].next_game_slot = "radiant"
            games[0].save()

            games[1].next_game = games[3]
            games[1].next_game_slot = "dire"
            games[1].save()

            games[2].next_game = games[4]
            games[2].next_game_slot = "radiant"
            games[2].save()

            games[3].next_game = games[5]
            games[3].next_game_slot = "radiant"
            games[3].save()

            games[4].next_game = games[5]
            games[4].next_game_slot = "dire"
            games[4].save()

            # Set up loser_next_game links for double elimination
            # Winners R1 M1 loser -> Losers R1 as radiant
            games[0].loser_next_game = games[2]
            games[0].loser_next_game_slot = "radiant"
            games[0].save()

            # Winners R1 M2 loser -> Losers R1 as dire
            games[1].loser_next_game = games[2]
            games[1].loser_next_game_slot = "dire"
            games[1].save()

            # Winners Final loser -> Losers Final as dire
            games[3].loser_next_game = games[4]
            games[3].loser_next_game_slot = "dire"
            games[3].save()

        completed_games = len([g for g in games if g.status == "completed"])
        pending_games = len([g for g in games if g.status == "pending"])
        print(
            f"Tournament '{tournament.name}': {completed_games} completed, {pending_games} pending games"
        )

    # Flush Redis cache to ensure bracket data is fresh
    flush_redis_cache()
