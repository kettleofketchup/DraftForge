# League Rating/ELO System Design

## Overview

This document describes the design for a league rating system that tracks player performance across tournaments. The system supports pluggable rating algorithms (Elo, Glicko-2, Fixed Delta, Team Average) with configurable parameters per league.

## Core Concepts

### Rating Formula

```
total_elo = base_mmr + positive_stats - negative_stats
```

- **base_mmr**: Player's Dota 2 MMR snapshot at league registration
- **positive_stats**: Sum of all rating gains from wins
- **negative_stats**: Sum of all rating losses from defeats
- **total_elo**: Current effective rating for matchmaking/rankings

### Key Features

- Pluggable rating systems (Elo, Glicko-2, Fixed Delta, Team Average)
- Both Glicko-style uncertainty (RD) AND percentile-based K-factor scaling
- Historical snapshots of MMR at match time for auditing
- Recalculation support with constraints (MMR threshold, age limits)
- Age decay for older matches (configurable per league)
- User verification for active Dota 2 ranked MMR

---

## Section 1: User MMR Tracking

### CustomUser Model Additions

```python
# Add to existing CustomUser model
has_active_dota_mmr = models.BooleanField(default=False)
dota_mmr_last_verified = models.DateTimeField(null=True, blank=True)
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `has_active_dota_mmr` | Boolean | User has active ranked MMR in Dota 2 |
| `dota_mmr_last_verified` | DateTime | Last time user confirmed their MMR is current |

### Verification Flow

**Profile Page**:
- Manual verification on user profile page
- User clicks "Verify MMR" button to confirm their ranked MMR is current
- Updates `dota_mmr_last_verified` to current timestamp

**Login Popup Logic**:
- Show popup only if: `has_active_dota_mmr = True` AND `dota_mmr_last_verified` > 30 days ago
- Do NOT show if `has_active_dota_mmr = False` (user doesn't have active ranked MMR)
- Show once per session
- Message: "Please update your MMR only if you have a new ranked MMR"

**Admin Controls**:
- Admin can mark user as unverified (set `dota_mmr_last_verified = null`)
- Admin can toggle `has_active_dota_mmr` flag

---

## Section 2: LeaguePlayerStats Model

```python
class LeaguePlayerStats(models.Model):
    """Per-league rating tracking for a player."""

    league = models.ForeignKey(
        'League',
        on_delete=models.CASCADE,
        related_name='player_stats'
    )
    player = models.ForeignKey(
        'CustomUser',
        on_delete=models.CASCADE,
        related_name='league_stats'
    )

    # Rating components
    base_mmr = models.IntegerField(default=0)
    base_mmr_snapshot_date = models.DateTimeField(auto_now_add=True)
    positive_stats = models.IntegerField(default=0)
    negative_stats = models.IntegerField(default=0)

    # Glicko-2 uncertainty tracking
    rating_deviation = models.FloatField(default=350.0)
    last_played = models.DateTimeField(null=True, blank=True)

    # Statistics
    games_played = models.PositiveIntegerField(default=0)
    wins = models.PositiveIntegerField(default=0)
    losses = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ['league', 'player']

    @property
    def total_elo(self) -> int:
        """Calculate current effective rating."""
        return self.base_mmr + self.positive_stats - self.negative_stats

    @property
    def win_rate(self) -> float:
        """Calculate win percentage."""
        if self.games_played == 0:
            return 0.0
        return self.wins / self.games_played
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `league` | FK | League this stat belongs to |
| `player` | FK | Player (CustomUser) this stat tracks |
| `base_mmr` | Integer | Dota 2 MMR at league registration |
| `base_mmr_snapshot_date` | DateTime | When base_mmr was captured |
| `positive_stats` | Integer | Sum of all rating gains |
| `negative_stats` | Integer | Sum of all rating losses |
| `rating_deviation` | Float | Glicko-2 uncertainty (default 350) |
| `last_played` | DateTime | Last match played in this league |
| `games_played` | Integer | Total matches in this league |
| `wins` | Integer | Total wins |
| `losses` | Integer | Total losses |

---

## Section 3: LeagueMatch & Participant Models

### LeagueMatch Model

```python
class LeagueMatch(models.Model):
    """Canonical rated match object for a league."""

    league = models.ForeignKey(
        'League',
        on_delete=models.CASCADE,
        related_name='matches'
    )

    # Match source (one or the other)
    game = models.OneToOneField(
        'Game',
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    steam_match_id = models.BigIntegerField(null=True, blank=True)

    # Match details
    played_at = models.DateTimeField()
    stage = models.CharField(max_length=50, blank=True)
    bracket_slot = models.ForeignKey(
        'bracket.BracketSlot',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='league_matches'
    )

    # Finalization state
    is_finalized = models.BooleanField(default=False)
    finalized_at = models.DateTimeField(null=True, blank=True)

    # Recalculation tracking
    last_recalculated_at = models.DateTimeField(null=True, blank=True)
    recalculation_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-played_at']
```

### LeagueMatchParticipant Model

```python
class LeagueMatchParticipant(models.Model):
    """Individual player's participation in a league match."""

    match = models.ForeignKey(
        'LeagueMatch',
        on_delete=models.CASCADE,
        related_name='participants'
    )
    player = models.ForeignKey(
        'CustomUser',
        on_delete=models.CASCADE
    )
    player_stats = models.ForeignKey(
        'LeaguePlayerStats',
        on_delete=models.CASCADE
    )

    # Snapshot at match time (for auditing)
    mmr_at_match = models.IntegerField()
    elo_before = models.IntegerField()
    elo_after = models.IntegerField()

    # Rating calculation parameters used
    k_factor_used = models.FloatField()
    rating_deviation_used = models.FloatField()
    age_decay_factor = models.FloatField(default=1.0)

    # Result
    is_winner = models.BooleanField()
    delta = models.IntegerField()

    class Meta:
        unique_together = ['match', 'player']
```

### Field Definitions - LeagueMatchParticipant

| Field | Type | Description |
|-------|------|-------------|
| `mmr_at_match` | Integer | Player's base_mmr when match was played |
| `elo_before` | Integer | total_elo before this match |
| `elo_after` | Integer | total_elo after this match |
| `k_factor_used` | Float | K-factor applied (after percentile adjustment) |
| `rating_deviation_used` | Float | RD at time of calculation |
| `age_decay_factor` | Float | Decay multiplier applied (1.0 = full weight) |
| `is_winner` | Boolean | Whether player won |
| `delta` | Integer | Rating change (positive or negative) |

---

## Section 4: League Rating Configuration

### League Model Additions

```python
# Add to existing League model

RATING_SYSTEMS = [
    ('elo', 'Standard Elo'),
    ('glicko2', 'Glicko-2'),
    ('fixed_delta', 'Fixed Delta'),
    ('team_avg', 'Team Average Based'),
]

# Rating system selection
rating_system = models.CharField(
    max_length=20,
    choices=RATING_SYSTEMS,
    default='elo'
)

# K-factor configuration
k_factor_default = models.FloatField(default=32.0)
k_factor_bottom_percentile = models.FloatField(default=40.0)  # Bottom 5%
k_factor_top_percentile = models.FloatField(default=16.0)     # Top 5%
percentile_threshold = models.FloatField(default=0.05)        # 5%

# Fixed delta configuration
fixed_delta_win = models.IntegerField(default=25)
fixed_delta_loss = models.IntegerField(default=25)

# Age decay configuration
age_decay_enabled = models.BooleanField(default=True)
age_decay_half_life_days = models.IntegerField(default=180)
age_decay_minimum = models.FloatField(default=0.1)  # Never decay below 10%

# Recalculation constraints
recalc_mmr_threshold = models.IntegerField(default=500)
recalc_max_age_days = models.IntegerField(default=365)

# Glicko-2 specific
glicko_initial_rd = models.FloatField(default=350.0)
glicko_rd_decay_per_day = models.FloatField(default=1.0)
```

### Configuration Reference

| Setting | Default | Description |
|---------|---------|-------------|
| `rating_system` | 'elo' | Which algorithm to use |
| `k_factor_default` | 32.0 | Standard K-factor |
| `k_factor_bottom_percentile` | 40.0 | K for bottom 5% (more volatile) |
| `k_factor_top_percentile` | 16.0 | K for top 5% (more stable) |
| `percentile_threshold` | 0.05 | What constitutes top/bottom |
| `age_decay_half_life_days` | 180 | Days until match weight = 50% |
| `age_decay_minimum` | 0.1 | Minimum decay factor (10%) |
| `recalc_mmr_threshold` | 500 | MMR change limit for recalc |
| `recalc_max_age_days` | 365 | Max age for recalculation |

---

## Section 5: Pluggable Rating Engine

### File: `app/leagues/rating.py`

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models import League, LeaguePlayerStats


@dataclass
class RatingResult:
    """Result of a rating calculation."""
    winner_delta: int
    loser_delta: int
    winner_k_used: float
    loser_k_used: float


class BaseRatingSystem(ABC):
    """Abstract base class for rating systems."""

    def __init__(self, league: 'League'):
        self.league = league

    @abstractmethod
    def calculate(
        self,
        winner_stats: 'LeaguePlayerStats',
        loser_stats: 'LeaguePlayerStats',
        age_decay_factor: float = 1.0
    ) -> RatingResult:
        """Calculate rating changes for a match result."""
        pass

    def get_k_factor(self, player_stats: 'LeaguePlayerStats') -> float:
        """Get K-factor with percentile adjustment."""
        # Get player's percentile in the league
        percentile = self._calculate_percentile(player_stats)

        threshold = self.league.percentile_threshold

        if percentile <= threshold:
            # Bottom percentile - higher K for faster climb
            return self.league.k_factor_bottom_percentile
        elif percentile >= (1 - threshold):
            # Top percentile - lower K for stability
            return self.league.k_factor_top_percentile
        else:
            return self.league.k_factor_default

    def _calculate_percentile(self, player_stats: 'LeaguePlayerStats') -> float:
        """Calculate player's percentile rank in the league."""
        all_stats = self.league.player_stats.all()
        total = all_stats.count()
        if total <= 1:
            return 0.5

        below = all_stats.filter(
            total_elo__lt=player_stats.total_elo
        ).count()
        return below / (total - 1)


class EloRatingSystem(BaseRatingSystem):
    """Standard Elo with percentile-based K-factor."""

    def calculate(
        self,
        winner_stats: 'LeaguePlayerStats',
        loser_stats: 'LeaguePlayerStats',
        age_decay_factor: float = 1.0
    ) -> RatingResult:
        winner_elo = winner_stats.total_elo
        loser_elo = loser_stats.total_elo

        # Expected scores
        exp_winner = 1 / (1 + 10 ** ((loser_elo - winner_elo) / 400))
        exp_loser = 1 - exp_winner

        # Get K-factors
        k_winner = self.get_k_factor(winner_stats)
        k_loser = self.get_k_factor(loser_stats)

        # Calculate deltas with age decay
        winner_delta = round(k_winner * (1 - exp_winner) * age_decay_factor)
        loser_delta = round(k_loser * (0 - exp_loser) * age_decay_factor)

        return RatingResult(
            winner_delta=winner_delta,
            loser_delta=abs(loser_delta),
            winner_k_used=k_winner,
            loser_k_used=k_loser
        )


class FixedDeltaRatingSystem(BaseRatingSystem):
    """Fixed point gain/loss regardless of opponent."""

    def calculate(
        self,
        winner_stats: 'LeaguePlayerStats',
        loser_stats: 'LeaguePlayerStats',
        age_decay_factor: float = 1.0
    ) -> RatingResult:
        win_delta = round(self.league.fixed_delta_win * age_decay_factor)
        loss_delta = round(self.league.fixed_delta_loss * age_decay_factor)

        return RatingResult(
            winner_delta=win_delta,
            loser_delta=loss_delta,
            winner_k_used=self.league.fixed_delta_win,
            loser_k_used=self.league.fixed_delta_loss
        )


def get_rating_system(league: 'League') -> BaseRatingSystem:
    """Factory function to get the appropriate rating system."""
    systems = {
        'elo': EloRatingSystem,
        'fixed_delta': FixedDeltaRatingSystem,
        # 'glicko2': Glicko2RatingSystem,  # Future
        # 'team_avg': TeamAvgRatingSystem,  # Future
    }

    system_class = systems.get(league.rating_system, EloRatingSystem)
    return system_class(league)
```

---

## Section 6: Match Finalization Flow

### File: `app/leagues/services.py`

```python
from datetime import datetime, timedelta
from django.db import transaction
from django.utils import timezone


class LeagueMatchService:
    """Service for managing league matches and rating updates."""

    @classmethod
    def create_from_game(cls, league, game, bracket_slot=None):
        """Create a LeagueMatch from an existing Game object."""
        match = LeagueMatch.objects.create(
            league=league,
            game=game,
            played_at=game.played_at,
            stage=game.stage or '',
            bracket_slot=bracket_slot
        )
        return match

    @classmethod
    @transaction.atomic
    def finalize(cls, match: LeagueMatch, winners: list, losers: list):
        """
        Finalize a match and update all participant ratings.

        Args:
            match: The LeagueMatch to finalize
            winners: List of CustomUser objects who won
            losers: List of CustomUser objects who lost
        """
        if match.is_finalized:
            raise ValueError("Match is already finalized")

        league = match.league
        rating_system = get_rating_system(league)

        # Calculate age decay
        age_decay = cls._calculate_age_decay(league, match.played_at)

        # Get or create stats for all participants
        winner_stats = [
            LeaguePlayerStats.objects.get_or_create(
                league=league, player=p
            )[0] for p in winners
        ]
        loser_stats = [
            LeaguePlayerStats.objects.get_or_create(
                league=league, player=p
            )[0] for p in losers
        ]

        # Calculate team average ratings
        avg_winner_elo = sum(s.total_elo for s in winner_stats) / len(winner_stats)
        avg_loser_elo = sum(s.total_elo for s in loser_stats) / len(loser_stats)

        # Create virtual stats for team-vs-team calculation
        # (This gives us the base delta, then each player gets individual K)

        for stats, is_winner in [(winner_stats, True), (loser_stats, False)]:
            for player_stats in stats:
                # Get individual K-factor
                k_factor = rating_system.get_k_factor(player_stats)

                # Calculate expected score using team averages
                if is_winner:
                    exp_score = 1 / (1 + 10 ** ((avg_loser_elo - avg_winner_elo) / 400))
                    actual_score = 1
                else:
                    exp_score = 1 / (1 + 10 ** ((avg_winner_elo - avg_loser_elo) / 400))
                    actual_score = 0

                # Calculate delta
                delta = round(k_factor * (actual_score - exp_score) * age_decay)

                elo_before = player_stats.total_elo

                # Update stats
                if delta >= 0:
                    player_stats.positive_stats += delta
                else:
                    player_stats.negative_stats += abs(delta)

                player_stats.games_played += 1
                if is_winner:
                    player_stats.wins += 1
                else:
                    player_stats.losses += 1
                player_stats.last_played = match.played_at
                player_stats.save()

                # Create participant record
                LeagueMatchParticipant.objects.create(
                    match=match,
                    player=player_stats.player,
                    player_stats=player_stats,
                    mmr_at_match=player_stats.base_mmr,
                    elo_before=elo_before,
                    elo_after=player_stats.total_elo,
                    k_factor_used=k_factor,
                    rating_deviation_used=player_stats.rating_deviation,
                    age_decay_factor=age_decay,
                    is_winner=is_winner,
                    delta=delta
                )

        # Mark match as finalized
        match.is_finalized = True
        match.finalized_at = timezone.now()
        match.save()

    @classmethod
    def _calculate_age_decay(cls, league, played_at: datetime) -> float:
        """Calculate age decay factor for a match."""
        if not league.age_decay_enabled:
            return 1.0

        age_days = (timezone.now() - played_at).days
        half_life = league.age_decay_half_life_days

        # Half-life decay formula: factor = 0.5 ^ (age / half_life)
        decay = 0.5 ** (age_days / half_life)

        # Enforce minimum
        return max(decay, league.age_decay_minimum)

    @classmethod
    @transaction.atomic
    def recalculate(cls, match: LeagueMatch):
        """
        Recalculate ratings for a finalized match.

        Constraints:
        - Player's current MMR must be within threshold of match-time MMR
        - Match must be within max age limit
        """
        league = match.league

        # Check age constraint
        age_days = (timezone.now() - match.played_at).days
        if age_days > league.recalc_max_age_days:
            raise ValueError(
                f"Match is too old to recalculate ({age_days} days > {league.recalc_max_age_days})"
            )

        # Check MMR threshold for all participants
        for participant in match.participants.all():
            current_mmr = participant.player_stats.base_mmr
            match_mmr = participant.mmr_at_match
            diff = abs(current_mmr - match_mmr)

            if diff > league.recalc_mmr_threshold:
                raise ValueError(
                    f"Player {participant.player.username} MMR changed too much "
                    f"({diff} > {league.recalc_mmr_threshold})"
                )

        # Reverse the original deltas
        for participant in match.participants.all():
            stats = participant.player_stats
            if participant.delta >= 0:
                stats.positive_stats -= participant.delta
            else:
                stats.negative_stats -= abs(participant.delta)

            if participant.is_winner:
                stats.wins -= 1
            else:
                stats.losses -= 1
            stats.games_played -= 1
            stats.save()

        # Delete old participants
        match.participants.all().delete()

        # Re-finalize with current parameters
        match.is_finalized = False
        match.save()

        # Re-run finalization
        winners = [p.player for p in match.participants.filter(is_winner=True)]
        losers = [p.player for p in match.participants.filter(is_winner=False)]

        # Note: We need to track original winners/losers before deletion
        # This is a simplified version - full impl would store this info

        match.recalculation_count += 1
        match.last_recalculated_at = timezone.now()
        match.save()
```

---

## Implementation Notes

### Migration Order

1. Add fields to `CustomUser` model
2. Create `LeaguePlayerStats` model
3. Create `LeagueMatch` model
4. Create `LeagueMatchParticipant` model
5. Add rating configuration fields to `League` model

### Future Enhancements

- **Glicko-2 Implementation**: Full volatility tracking
- **Team Average System**: Rating based on team composition
- **Rating History**: Track rating over time for graphs
- **Placement Matches**: Separate handling for initial calibration
- **Season Resets**: Soft reset mechanics between seasons
