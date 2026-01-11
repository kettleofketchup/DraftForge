import logging
from datetime import datetime
from datetime import timezone as dt_timezone

from app.models import Game, Tournament
from steam.models import GameMatchSuggestion, Match

log = logging.getLogger(__name__)


def check_match_for_games(match):
    """
    Called during sync. Check if new match corresponds to any unlinked tournament games.
    Auto-link or create suggestion based on confidence.

    High confidence (auto-link): All 10 players match AND match date within tournament range
    Partial matches: Store as GameMatchSuggestion for manual review
    """
    # Get steam_ids from the match
    match_steam_ids = set(match.players.values_list("steam_id", flat=True))

    if not match_steam_ids:
        return

    # Find tournaments that were active around this match's time
    match_datetime = datetime.fromtimestamp(match.start_time, tz=dt_timezone.utc)
    match_date = match_datetime.date()

    # Look for tournaments on the same day as the match
    # (since Tournament only has date_played, not start_date/end_date)
    active_tournaments = Tournament.objects.filter(date_played=match_date)

    for tournament in active_tournaments:
        # Get unlinked games in this tournament
        unlinked_games = Game.objects.filter(
            tournament=tournament, gameid__isnull=True
        ).select_related("radiant_team", "dire_team")

        for game in unlinked_games:
            # Calculate player overlap
            game_steam_ids = _get_game_player_steam_ids(game)
            overlap = len(match_steam_ids & game_steam_ids)

            if overlap == 0:
                continue

            # Calculate confidence score (0.0 to 1.0)
            # Perfect match = 10 players overlap out of 10
            confidence = overlap / 10.0

            # Check if suggestion already exists
            existing = GameMatchSuggestion.objects.filter(
                game=game, match=match
            ).first()

            if existing:
                continue

            if confidence == 1.0:
                # High confidence - auto-link and set winner
                _link_game_to_match(game, match)

                GameMatchSuggestion.objects.create(
                    game=game,
                    match=match,
                    tournament=tournament,
                    confidence_score=confidence,
                    player_overlap=overlap,
                    auto_linked=True,
                )
                log.info(f"Auto-linked game {game.id} to match {match.match_id}")
            else:
                # Partial match - create suggestion for review
                GameMatchSuggestion.objects.create(
                    game=game,
                    match=match,
                    tournament=tournament,
                    confidence_score=confidence,
                    player_overlap=overlap,
                    auto_linked=False,
                )


def _get_game_player_steam_ids(game):
    """Get set of steam_ids for players in both teams of a game."""
    steam_ids = set()

    if game.radiant_team:
        radiant_ids = game.radiant_team.members.exclude(
            steamid__isnull=True
        ).values_list("steamid", flat=True)
        steam_ids.update(radiant_ids)

    if game.dire_team:
        dire_ids = game.dire_team.members.exclude(steamid__isnull=True).values_list(
            "steamid", flat=True
        )
        steam_ids.update(dire_ids)

    return steam_ids


def _determine_winner_from_match(game, match):
    """
    Determine which tournament team won based on Steam match data.

    Uses player_slot to determine which team was radiant/dire:
    - player_slot 0-4 = radiant
    - player_slot 128-132 = dire

    Returns: The winning Team object, or None if unable to determine
    """
    if not game.radiant_team or not game.dire_team:
        return None

    # Get steam_ids for each tournament team
    radiant_team_steam_ids = set(
        game.radiant_team.members.exclude(steamid__isnull=True).values_list(
            "steamid", flat=True
        )
    )
    dire_team_steam_ids = set(
        game.dire_team.members.exclude(steamid__isnull=True).values_list(
            "steamid", flat=True
        )
    )

    # Get players from match grouped by side (using player_slot)
    match_radiant_steam_ids = set(
        match.players.filter(player_slot__lt=128).values_list("steam_id", flat=True)
    )
    match_dire_steam_ids = set(
        match.players.filter(player_slot__gte=128).values_list("steam_id", flat=True)
    )

    # Calculate overlap for each possible mapping
    # Option A: tournament radiant = match radiant, tournament dire = match dire
    radiant_as_radiant = len(radiant_team_steam_ids & match_radiant_steam_ids)
    dire_as_dire = len(dire_team_steam_ids & match_dire_steam_ids)
    option_a_score = radiant_as_radiant + dire_as_dire

    # Option B: tournament radiant = match dire, tournament dire = match radiant
    radiant_as_dire = len(radiant_team_steam_ids & match_dire_steam_ids)
    dire_as_radiant = len(dire_team_steam_ids & match_radiant_steam_ids)
    option_b_score = radiant_as_dire + dire_as_radiant

    if option_a_score == 0 and option_b_score == 0:
        log.warning(f"Cannot determine team mapping for game {game.id}")
        return None

    # Determine which mapping is correct
    if option_a_score >= option_b_score:
        # Tournament teams match their names (radiant=radiant, dire=dire)
        if match.radiant_win:
            winner = game.radiant_team
        else:
            winner = game.dire_team
    else:
        # Tournament teams are swapped (radiant played as dire, dire played as radiant)
        if match.radiant_win:
            winner = game.dire_team
        else:
            winner = game.radiant_team

    log.info(
        f"Game {game.id}: Determined winner is {winner.name} "
        f"(option_a={option_a_score}, option_b={option_b_score}, radiant_win={match.radiant_win})"
    )
    return winner


def _link_game_to_match(game, match):
    """
    Link a game to a match and set the winner based on match data.

    Updates:
    - game.gameid = match.match_id
    - game.winning_team = determined from match.radiant_win and player positions
    - game.status = "completed"
    """
    from cacheops import invalidate_obj

    game.gameid = match.match_id

    winner = _determine_winner_from_match(game, match)
    if winner:
        game.winning_team = winner
        game.status = "completed"
        log.info(
            f"Linked game {game.id} to match {match.match_id}, winner: {winner.name}"
        )
    else:
        log.warning(
            f"Linked game {game.id} to match {match.match_id}, but could not determine winner"
        )

    game.save(update_fields=["gameid", "winning_team", "status"])

    # Invalidate cache for game and tournament
    invalidate_obj(game)
    if game.tournament:
        invalidate_obj(game.tournament)


def get_suggestions_for_tournament(tournament_id):
    """
    Retrieve all GameMatchSuggestion records for a tournament,
    ordered by confidence score descending.

    Returns: QuerySet of GameMatchSuggestion with game and match prefetched
    """
    return (
        GameMatchSuggestion.objects.filter(tournament_id=tournament_id)
        .select_related("game", "match")
        .prefetch_related("match__players")
        .order_by("-confidence_score")
    )


def get_suggestions_for_game(game_id):
    """
    Get all match suggestions for a specific tournament game,
    ordered by confidence score descending.

    Returns: QuerySet of GameMatchSuggestion with match and player stats prefetched
    """
    return (
        GameMatchSuggestion.objects.filter(game_id=game_id)
        .select_related("match")
        .prefetch_related("match__players")
        .order_by("-confidence_score")
    )


def confirm_suggestion(suggestion_id):
    """
    Staff confirms a suggestion - sets Game.gameid to the match ID
    and marks suggestion as auto_linked=True.

    Returns: True if successful, False if suggestion not found or already linked
    """
    try:
        suggestion = GameMatchSuggestion.objects.select_related("game", "match").get(
            id=suggestion_id
        )
    except GameMatchSuggestion.DoesNotExist:
        return False

    if suggestion.game.gameid is not None:
        # Game already linked
        return False

    _link_game_to_match(suggestion.game, suggestion.match)

    suggestion.auto_linked = True
    suggestion.save(update_fields=["auto_linked"])

    return True


def dismiss_suggestion(suggestion_id):
    """
    Staff dismisses a suggestion - deletes the GameMatchSuggestion record.

    Returns: True if deleted, False if not found
    """
    try:
        suggestion = GameMatchSuggestion.objects.get(id=suggestion_id)
        suggestion.delete()
        return True
    except GameMatchSuggestion.DoesNotExist:
        return False


def auto_link_matches_for_tournament(tournament_id):
    """
    Scan all games in tournament, find matching Steam matches.
    Auto-link exact matches (10/10 players + correct date),
    store suggestions for partial matches.

    Returns: dict with {auto_linked_count, suggestions_created_count}
    """
    try:
        tournament = Tournament.objects.get(id=tournament_id)
    except Tournament.DoesNotExist:
        return {"auto_linked_count": 0, "suggestions_created_count": 0}

    auto_linked_count = 0
    suggestions_created_count = 0

    # Get all unlinked games in this tournament
    unlinked_games = Game.objects.filter(
        tournament=tournament, gameid__isnull=True
    ).select_related("radiant_team", "dire_team")

    for game in unlinked_games:
        # Get steam_ids from game's teams
        game_steam_ids = _get_game_player_steam_ids(game)

        if not game_steam_ids:
            continue

        # Find matches that have player overlap
        candidate_matches = (
            Match.objects.filter(players__steam_id__in=game_steam_ids)
            .distinct()
            .prefetch_related("players")
        )

        for match in candidate_matches:
            match_steam_ids = set(match.players.values_list("steam_id", flat=True))
            overlap = len(match_steam_ids & game_steam_ids)

            if overlap == 0:
                continue

            confidence = overlap / 10.0

            # Check if suggestion already exists
            if GameMatchSuggestion.objects.filter(game=game, match=match).exists():
                continue

            if confidence == 1.0:
                # Perfect match - auto-link and set winner
                _link_game_to_match(game, match)

                GameMatchSuggestion.objects.create(
                    game=game,
                    match=match,
                    tournament=tournament,
                    confidence_score=confidence,
                    player_overlap=overlap,
                    auto_linked=True,
                )
                auto_linked_count += 1
                break  # Game is now linked, move to next game
            else:
                # Partial match - create suggestion
                GameMatchSuggestion.objects.create(
                    game=game,
                    match=match,
                    tournament=tournament,
                    confidence_score=confidence,
                    player_overlap=overlap,
                    auto_linked=False,
                )
                suggestions_created_count += 1

    return {
        "auto_linked_count": auto_linked_count,
        "suggestions_created_count": suggestions_created_count,
    }
