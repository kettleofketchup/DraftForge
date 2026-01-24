"""Rating calculation systems for league matches."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Dict, List

if TYPE_CHECKING:
    from app.models import League, LeagueRating


class RatingSystem(ABC):
    """Base class for rating calculation systems."""

    def __init__(self, league: "League"):
        self.league = league

    @abstractmethod
    def calculate_team_deltas(
        self,
        winners: List["LeagueRating"],
        losers: List["LeagueRating"],
        age_decay_factor: float = 1.0,
    ) -> Dict:
        """
        Calculate rating deltas for a team match.

        Args:
            winners: List of LeagueRating objects for winning team
            losers: List of LeagueRating objects for losing team
            age_decay_factor: Decay factor for older matches (0.0-1.0)

        Returns:
            Dict with keys:
            - winner_delta: Positive rating change for winners
            - loser_delta: Positive value (will be subtracted from losers)
            - winner_k_factors: Dict mapping player_id to K-factor used
            - loser_k_factors: Dict mapping player_id to K-factor used
        """
        pass

    def _get_k_factor(self, rating: "LeagueRating") -> float:
        """Get K-factor for a player based on games played."""
        if rating.games_played < self.league.placement_games:
            return self.league.k_factor_placement
        return self.league.k_factor_default


class EloRatingSystem(RatingSystem):
    """Standard Elo rating system with team averaging."""

    def calculate_team_deltas(
        self,
        winners: List["LeagueRating"],
        losers: List["LeagueRating"],
        age_decay_factor: float = 1.0,
    ) -> Dict:
        """
        Calculate Elo rating changes for team match.

        Uses team average Elo to calculate expected score,
        then applies individual K-factors.
        """
        if not winners or not losers:
            raise ValueError("Both winners and losers lists must be non-empty")

        # Calculate team averages
        winner_avg = sum(r.total_elo for r in winners) / len(winners)
        loser_avg = sum(r.total_elo for r in losers) / len(losers)

        # Calculate expected score for winners
        # E = 1 / (1 + 10^((opponent_rating - player_rating) / 400))
        expected_winner = 1 / (1 + 10 ** ((loser_avg - winner_avg) / 400))

        # Actual score: 1 for win, 0 for loss
        actual_winner = 1.0

        # Calculate K-factors for each player
        winner_k_factors = {r.player_id: self._get_k_factor(r) for r in winners}
        loser_k_factors = {r.player_id: self._get_k_factor(r) for r in losers}

        # Use average K-factor for team delta
        avg_winner_k = sum(winner_k_factors.values()) / len(winner_k_factors)
        avg_loser_k = sum(loser_k_factors.values()) / len(loser_k_factors)

        # Calculate base delta: K * (actual - expected)
        winner_delta = (
            avg_winner_k * (actual_winner - expected_winner) * age_decay_factor
        )
        loser_delta = (
            avg_loser_k * (1 - actual_winner - (1 - expected_winner)) * age_decay_factor
        )

        # Ensure positive loser_delta (it will be subtracted)
        loser_delta = abs(loser_delta)

        return {
            "winner_delta": winner_delta,
            "loser_delta": loser_delta,
            "winner_k_factors": winner_k_factors,
            "loser_k_factors": loser_k_factors,
        }


class FixedDeltaRatingSystem(RatingSystem):
    """Fixed rating change per match (ignores team strength)."""

    def calculate_team_deltas(
        self,
        winners: List["LeagueRating"],
        losers: List["LeagueRating"],
        age_decay_factor: float = 1.0,
    ) -> Dict:
        """
        Calculate fixed rating changes.

        All winners gain fixed_delta, all losers lose fixed_delta.
        """
        if not winners or not losers:
            raise ValueError("Both winners and losers lists must be non-empty")

        delta = self.league.fixed_delta * age_decay_factor

        # K-factors not used but returned for consistency
        winner_k_factors = {r.player_id: self.league.fixed_delta for r in winners}
        loser_k_factors = {r.player_id: self.league.fixed_delta for r in losers}

        return {
            "winner_delta": delta,
            "loser_delta": delta,
            "winner_k_factors": winner_k_factors,
            "loser_k_factors": loser_k_factors,
        }


def get_rating_system(league: "League") -> RatingSystem:
    """Factory function to get appropriate rating system for a league."""
    systems = {
        "elo": EloRatingSystem,
        "fixed_delta": FixedDeltaRatingSystem,
    }

    system_class = systems.get(league.rating_system)
    if not system_class:
        raise ValueError(f"Unknown rating system: {league.rating_system}")

    return system_class(league)
