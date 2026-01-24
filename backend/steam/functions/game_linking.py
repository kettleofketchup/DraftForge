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


def _build_captain_match_index(matches: list, captain_steam_ids: set) -> dict:
    """
    Build an index of captain_steam_id -> [matches in time order].

    Args:
        matches: List of Match objects sorted by start_time
        captain_steam_ids: Set of captain Steam IDs to track

    Returns:
        Dict mapping steam_id -> list of (match, match_index) tuples in time order
    """
    captain_matches = {steam_id: [] for steam_id in captain_steam_ids}

    for match in matches:
        match_steam_ids = set(match.players.values_list("steam_id", flat=True))
        for captain_id in captain_steam_ids:
            if captain_id in match_steam_ids:
                captain_matches[captain_id].append(match)

    return captain_matches


def auto_assign_matches_by_time(tournament_id, preview=True, min_overlap=4):
    """
    Smart auto-assign Steam matches to tournament games based on:
    1. Tournament day filtering (only matches from tournament date)
    2. Captain game sequence (captain's Nth bracket game → their Nth steam match)
    3. Player overlap validation (minimum threshold)

    The algorithm:
    - For each bracket game, calculate which game number it is for each captain
      (e.g., Losers R2 = captain's 3rd game)
    - Find that captain's Nth steam match on tournament day
    - Validate with player overlap

    This is smarter than pure time ordering because it accounts for:
    - Losers bracket games happening after winners games
    - A captain's journey through the bracket

    Args:
        tournament_id: ID of the tournament
        preview: If True, returns assignments without applying them
        min_overlap: Minimum player overlap required (default 4)

    Returns: dict with assignments and metadata
    """
    try:
        tournament = Tournament.objects.get(id=tournament_id)
    except Tournament.DoesNotExist:
        return {"assignments": [], "linked_count": 0, "error": "Tournament not found"}

    # Get tournament date
    tournament_date = tournament.date_played.date()

    from datetime import datetime, time
    from datetime import timezone as dt_tz

    day_start = datetime.combine(tournament_date, time.min, tzinfo=dt_tz.utc)
    day_end = datetime.combine(tournament_date, time.max, tzinfo=dt_tz.utc)
    start_timestamp = int(day_start.timestamp())
    end_timestamp = int(day_end.timestamp())

    # Get ALL games in tournament (for tracking captain game sequence)
    all_games = list(
        Game.objects.filter(tournament=tournament)
        .select_related(
            "radiant_team__captain",
            "dire_team__captain",
        )
        .prefetch_related("radiant_team__members", "dire_team__members")
        .order_by("bracket_type", "round", "position")
    )

    # Collect all captain steam IDs
    captain_steam_ids = set()
    for game in all_games:
        if game.radiant_team and game.radiant_team.captain:
            if game.radiant_team.captain.steamid:
                captain_steam_ids.add(game.radiant_team.captain.steamid)
        if game.dire_team and game.dire_team.captain:
            if game.dire_team.captain.steamid:
                captain_steam_ids.add(game.dire_team.captain.steamid)

    # Get unlinked games
    unlinked_games = [g for g in all_games if g.gameid is None]

    if not unlinked_games:
        return {"assignments": [], "linked_count": 0, "message": "No unlinked games"}

    # Get steam matches from tournament day
    match_filter = {
        "start_time__gte": start_timestamp,
        "start_time__lte": end_timestamp,
    }
    if tournament.steam_league_id:
        match_filter["league_id"] = tournament.steam_league_id

    # Exclude already linked matches
    linked_match_ids = set(
        Game.objects.filter(tournament=tournament, gameid__isnull=False).values_list(
            "gameid", flat=True
        )
    )

    candidate_matches = list(
        Match.objects.filter(**match_filter)
        .exclude(match_id__in=linked_match_ids)
        .prefetch_related("players")
        .order_by("start_time")
    )

    if not candidate_matches:
        return {
            "assignments": [],
            "linked_count": 0,
            "message": "No steam matches found for tournament day",
        }

    # Build captain -> matches index (captain's matches in time order)
    captain_match_index = _build_captain_match_index(
        candidate_matches, captain_steam_ids
    )

    # Track which matches have been assigned
    used_match_ids = set()
    # Track how many games each captain has been assigned (to find their Nth match)
    captain_assigned_count = {steam_id: 0 for steam_id in captain_steam_ids}

    # First pass: count already-linked games per captain to establish baseline
    for game in all_games:
        if game.gameid is not None:  # Already linked
            if game.radiant_team and game.radiant_team.captain:
                captain_id = game.radiant_team.captain.steamid
                if captain_id:
                    captain_assigned_count[captain_id] = (
                        captain_assigned_count.get(captain_id, 0) + 1
                    )
            if game.dire_team and game.dire_team.captain:
                captain_id = game.dire_team.captain.steamid
                if captain_id:
                    captain_assigned_count[captain_id] = (
                        captain_assigned_count.get(captain_id, 0) + 1
                    )

    # Sort unlinked games by expected play order
    bracket_order = {"swiss": 0, "winners": 1, "losers": 2, "grand_finals": 3}
    unlinked_games.sort(
        key=lambda g: (bracket_order.get(g.bracket_type, 99), g.round, g.position)
    )

    assignments = []

    for game in unlinked_games:
        game_steam_ids = _get_game_player_steam_ids(game)
        if not game_steam_ids:
            continue

        # Get captain info
        radiant_captain_id = None
        dire_captain_id = None
        radiant_captain_name = None
        dire_captain_name = None

        if game.radiant_team and game.radiant_team.captain:
            radiant_captain_id = game.radiant_team.captain.steamid
            radiant_captain_name = game.radiant_team.captain.username
        if game.dire_team and game.dire_team.captain:
            dire_captain_id = game.dire_team.captain.steamid
            dire_captain_name = game.dire_team.captain.username

        # Get the actual game number for each captain (how many games they've played so far)
        radiant_game_num = (
            captain_assigned_count.get(radiant_captain_id, 0) + 1
            if radiant_captain_id
            else None
        )
        dire_game_num = (
            captain_assigned_count.get(dire_captain_id, 0) + 1
            if dire_captain_id
            else None
        )

        # Try to find a match using captain game sequence
        best_match = None
        best_overlap = 0
        match_method = "overlap"  # Track how we found the match

        # Strategy 1: Use captain's Nth match
        for captain_id in [radiant_captain_id, dire_captain_id]:
            if not captain_id or captain_id not in captain_match_index:
                continue

            captain_matches = captain_match_index[captain_id]
            # Which game number is this for the captain?
            # It's their (already_assigned + 1)th game
            game_index = captain_assigned_count.get(captain_id, 0)

            if game_index < len(captain_matches):
                potential_match = captain_matches[game_index]
                if potential_match.match_id not in used_match_ids:
                    # Validate with player overlap
                    match_steam_ids = set(
                        potential_match.players.values_list("steam_id", flat=True)
                    )
                    overlap = len(match_steam_ids & game_steam_ids)

                    if overlap >= min_overlap and overlap > best_overlap:
                        best_match = potential_match
                        best_overlap = overlap
                        match_method = "captain_sequence"

        # Strategy 2: Fallback to best overlap if captain sequence didn't work
        if not best_match:
            for match in candidate_matches:
                if match.match_id in used_match_ids:
                    continue

                match_steam_ids = set(match.players.values_list("steam_id", flat=True))
                overlap = len(match_steam_ids & game_steam_ids)

                if overlap >= min_overlap and overlap > best_overlap:
                    best_match = match
                    best_overlap = overlap
                    match_method = "overlap_fallback"

        if best_match:
            used_match_ids.add(best_match.match_id)

            # Update captain assigned counts
            if radiant_captain_id:
                captain_assigned_count[radiant_captain_id] = (
                    captain_assigned_count.get(radiant_captain_id, 0) + 1
                )
            if dire_captain_id:
                captain_assigned_count[dire_captain_id] = (
                    captain_assigned_count.get(dire_captain_id, 0) + 1
                )

            match_time = datetime.fromtimestamp(best_match.start_time, tz=dt_tz.utc)
            assignments.append(
                {
                    "game_id": game.id,
                    "game_round": game.round,
                    "game_position": game.position,
                    "bracket_type": game.bracket_type,
                    "match_id": best_match.match_id,
                    "start_time": best_match.start_time,
                    "start_time_display": match_time.strftime("%H:%M"),
                    "player_overlap": best_overlap,
                    "radiant_team": (
                        game.radiant_team.name if game.radiant_team else None
                    ),
                    "dire_team": game.dire_team.name if game.dire_team else None,
                    "radiant_captain": radiant_captain_name,
                    "dire_captain": dire_captain_name,
                    "radiant_game_num": radiant_game_num,
                    "dire_game_num": dire_game_num,
                    "match_method": match_method,
                }
            )

    # Apply assignments if not preview
    linked_count = 0
    if not preview:
        for assignment in assignments:
            try:
                game = Game.objects.get(id=assignment["game_id"])
                match = Match.objects.get(match_id=assignment["match_id"])
                _link_game_to_match(game, match)
                linked_count += 1
                log.info(
                    f"Auto-assigned game {game.id} ({game.bracket_type} R{game.round}) "
                    f"to match {match.match_id} via {assignment['match_method']} "
                    f"(overlap: {assignment['player_overlap']})"
                )
            except Exception as e:
                log.error(f"Failed to link game {assignment['game_id']}: {e}")

    return {
        "assignments": assignments,
        "linked_count": linked_count,
        "tournament_date": tournament_date.isoformat(),
        "total_unlinked_games": len(unlinked_games),
        "total_candidate_matches": len(candidate_matches),
    }


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
