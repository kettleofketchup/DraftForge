"""Match finalization service for league ratings."""

from datetime import datetime
from typing import List

from django.db import transaction
from django.utils import timezone


class LeagueMatchService:
    """Service for managing league matches and rating updates."""

    @classmethod
    def create_from_game(cls, league, game, bracket_slot=None):
        """Create a LeagueMatch from an existing Game object."""
        from app.models import LeagueMatch

        match = LeagueMatch.objects.create(
            league=league,
            game=game,
            played_at=game.updated_at or timezone.now(),
            stage=game.bracket_type or "",
            bracket_slot=bracket_slot,
        )
        return match

    @classmethod
    @transaction.atomic
    def finalize(cls, match, winners: List, losers: List, winning_side: str):
        """
        Finalize a match and update all participant ratings.

        Args:
            match: The LeagueMatch to finalize
            winners: List of CustomUser objects who won
            losers: List of CustomUser objects who lost
            winning_side: 'radiant' or 'dire'
        """
        from app.models import LeagueMatch, LeagueMatchParticipant, LeagueRating
        from app.services.rating import get_rating_system

        # Lock match row to prevent race condition
        match = LeagueMatch.objects.select_for_update().get(pk=match.pk)

        if match.is_finalized:
            raise ValueError("Match is already finalized")

        league = match.league
        rating_system = get_rating_system(league)

        # Calculate age decay
        age_decay = cls.calculate_age_decay(league, match.played_at)

        # Get or create ratings for all participants (batch lookup)
        all_players = winners + losers
        existing_ratings = {
            r.player_id: r
            for r in LeagueRating.objects.filter(
                league=league, player__in=all_players
            ).select_for_update()
        }

        # Create missing ratings
        for player in all_players:
            if player.pk not in existing_ratings:
                existing_ratings[player.pk] = LeagueRating.objects.create(
                    league=league, player=player, base_mmr=player.mmr or 0
                )

        winner_ratings = [existing_ratings[p.pk] for p in winners]
        loser_ratings = [existing_ratings[p.pk] for p in losers]

        # Calculate deltas using rating system
        result = rating_system.calculate_team_deltas(
            winners=winner_ratings, losers=loser_ratings, age_decay_factor=age_decay
        )

        winner_delta = result["winner_delta"]
        loser_delta = result["loser_delta"]
        winner_k_factors = result["winner_k_factors"]
        loser_k_factors = result["loser_k_factors"]

        losing_side = "dire" if winning_side == "radiant" else "radiant"

        # Update winner ratings and create participants
        for player, rating in zip(winners, winner_ratings):
            elo_before = rating.total_elo
            rating.positive_stats += winner_delta
            rating.games_played += 1
            rating.wins += 1
            rating.last_played = match.played_at
            rating.save()

            LeagueMatchParticipant.objects.create(
                match=match,
                player=player,
                player_rating=rating,
                team_side=winning_side,
                mmr_at_match=rating.base_mmr,
                elo_before=elo_before,
                elo_after=rating.total_elo,
                k_factor_used=winner_k_factors.get(player.pk, league.k_factor_default),
                rating_deviation_used=rating.rating_deviation,
                age_decay_factor=age_decay,
                is_winner=True,
                delta=winner_delta,
            )

        # Update loser ratings and create participants
        for player, rating in zip(losers, loser_ratings):
            elo_before = rating.total_elo
            rating.negative_stats += loser_delta
            rating.games_played += 1
            rating.losses += 1
            rating.last_played = match.played_at
            rating.save()

            LeagueMatchParticipant.objects.create(
                match=match,
                player=player,
                player_rating=rating,
                team_side=losing_side,
                mmr_at_match=rating.base_mmr,
                elo_before=elo_before,
                elo_after=rating.total_elo,
                k_factor_used=loser_k_factors.get(player.pk, league.k_factor_default),
                rating_deviation_used=rating.rating_deviation,
                age_decay_factor=age_decay,
                is_winner=False,
                delta=-loser_delta,  # Negative for losers
            )

        # Mark match as finalized
        match.is_finalized = True
        match.finalized_at = timezone.now()
        match.save()

        return match

    @classmethod
    def calculate_age_decay(cls, league, played_at: datetime) -> float:
        """Calculate age decay factor for a match."""
        if not league.age_decay_enabled:
            return 1.0

        now = timezone.now()
        if timezone.is_naive(played_at):
            played_at = timezone.make_aware(played_at)

        age_days = (now - played_at).days
        if age_days <= 0:
            return 1.0

        half_life = league.age_decay_half_life_days

        # Half-life decay formula: factor = 0.5 ^ (age / half_life)
        decay = 0.5 ** (age_days / half_life)

        # Enforce minimum
        return max(decay, league.age_decay_minimum)

    @classmethod
    @transaction.atomic
    def recalculate(cls, match):
        """
        Recalculate ratings for a finalized match.

        Reverses original deltas, then re-finalizes with current parameters.
        """
        from app.models import LeagueMatch

        # Lock match
        match = LeagueMatch.objects.select_for_update().get(pk=match.pk)
        league = match.league

        if not match.is_finalized:
            raise ValueError("Cannot recalculate unfinalized match")

        # Check age constraint
        age_days = (timezone.now() - match.played_at).days
        if age_days > league.recalc_max_age_days:
            raise ValueError(
                f"Match is too old to recalculate "
                f"({age_days} days > {league.recalc_max_age_days})"
            )

        # Store winner/loser info BEFORE deleting participants
        participants = list(
            match.participants.select_related("player", "player_rating")
        )
        winners = [p.player for p in participants if p.is_winner]
        losers = [p.player for p in participants if not p.is_winner]
        winning_side = next(
            (p.team_side for p in participants if p.is_winner), "radiant"
        )

        # Check MMR threshold for all participants
        for participant in participants:
            current_mmr = participant.player_rating.base_mmr
            match_mmr = participant.mmr_at_match
            diff = abs(current_mmr - match_mmr)

            if diff > league.recalc_mmr_threshold:
                raise ValueError(
                    f"Player {participant.player.username} MMR changed too much "
                    f"({diff} > {league.recalc_mmr_threshold})"
                )

        # Reverse the original deltas
        for participant in participants:
            rating = participant.player_rating
            if participant.is_winner:
                rating.positive_stats -= participant.delta
                rating.wins -= 1
            else:
                rating.negative_stats -= abs(participant.delta)
                rating.losses -= 1
            rating.games_played -= 1
            rating.save()

        # Delete old participants
        match.participants.all().delete()

        # Mark as not finalized for re-finalization
        match.is_finalized = False
        match.recalculation_count += 1
        match.last_recalculated_at = timezone.now()
        match.save()

        # Re-finalize with stored winner/loser lists
        return cls.finalize(match, winners, losers, winning_side)
