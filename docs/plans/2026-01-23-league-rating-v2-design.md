# League Rating System v2 Design

## Overview

This document supersedes the original `2026-01-21-league-rating-design.md` with a more comprehensive design that includes:

- **LeagueRatingConfig** as a separate model with ENUM-based defaults
- **Multiple K-factor modes**: placement, percentile, fixed, and hybrid
- **MMR Epoch system** to handle significant MMR changes
- **Full Glicko-2 implementation**
- **Player popup** displaying rating details per league configuration

---

## Core Problem: MMR Anchoring

**Scenario**: Player joins league with 1000 MMR, plays 10 games over a year, accumulates +200 rating. Their MMR is now 5000 (they improved IRL). Should those +200 points from playing against 1000 MMR opponents count toward their 5000 MMR rating?

**Answer**: No. When a player's verified MMR changes significantly, we start a new "epoch" - their old rating deltas no longer apply to their new skill level.

---

## Section 1: Enums and Constants

### File: `app/leagues/constants.py`

```python
from enum import Enum


class RatingSystem(str, Enum):
    """Available rating calculation algorithms."""
    ELO = "elo"
    GLICKO2 = "glicko2"
    FIXED_DELTA = "fixed_delta"

    @classmethod
    def choices(cls):
        return [(e.value, e.name.replace("_", " ").title()) for e in cls]


class KFactorMode(str, Enum):
    """K-factor calculation modes."""
    FIXED = "fixed"           # Same K for everyone
    PLACEMENT = "placement"   # Higher K for first N games
    PERCENTILE = "percentile" # K based on league standing
    HYBRID = "hybrid"         # Placement first, then percentile

    @classmethod
    def choices(cls):
        return [(e.value, e.name.replace("_", " ").title()) for e in cls]


class RatingDefaults(float, Enum):
    """Default values for rating configuration.

    These are the sensible defaults that leagues start with.
    Leagues can customize all of these values.
    """

    # === K-Factor Defaults ===
    K_FACTOR_DEFAULT = 32.0
    K_FACTOR_PLACEMENT = 64.0          # For players in placement games
    K_FACTOR_BOTTOM_PERCENTILE = 40.0  # For bottom 5% (faster climb)
    K_FACTOR_TOP_PERCENTILE = 16.0     # For top 5% (more stable)

    # === Percentile Configuration ===
    PERCENTILE_THRESHOLD = 0.05        # Top/bottom 5%

    # === Placement Configuration ===
    PLACEMENT_GAMES = 10               # Games before using standard K
    MIN_GAMES_FOR_RANKING = 3          # Minimum to appear on leaderboard

    # === Fixed Delta ===
    FIXED_DELTA_WIN = 25.0
    FIXED_DELTA_LOSS = 25.0

    # === Age Decay ===
    AGE_DECAY_HALF_LIFE_DAYS = 180.0   # 50% weight at 6 months
    AGE_DECAY_MINIMUM = 0.1            # Never below 10% weight

    # === Glicko-2 Specific ===
    GLICKO_INITIAL_RD = 350.0          # Initial rating deviation
    GLICKO_INITIAL_VOLATILITY = 0.06   # Initial volatility
    GLICKO_TAU = 0.5                   # System constant
    GLICKO_RD_DECAY_PER_DAY = 1.5      # RD increase per day of inactivity
    GLICKO_RD_MAX = 500.0              # Maximum RD (uncertainty cap)
    GLICKO_RD_MIN = 30.0               # Minimum RD (never fully certain)

    # === Recalculation Constraints ===
    RECALC_MAX_AGE_DAYS = 90.0         # Max age for recalculation
    RECALC_MMR_THRESHOLD = 500.0       # Max MMR change for recalc

    # === MMR Epoch ===
    MMR_EPOCH_THRESHOLD = 1000.0       # MMR change to trigger new epoch
    MMR_VERIFICATION_STALE_DAYS = 30.0 # Days before verification is stale


class DisplayRating(str, Enum):
    """What rating to display in UI."""
    TOTAL_ELO = "total_elo"           # base_mmr + positive - negative
    NET_CHANGE = "net_change"          # positive - negative only
    GLICKO_RATING = "glicko_rating"    # Glicko-2 rating (if using glicko2)
```

---

## Section 2: LeagueRatingConfig Model

### Design Rationale

Instead of embedding all rating configuration in the League model, we create a dedicated `LeagueRatingConfig` model:

1. **Separation of concerns** - Rating logic separate from league identity
2. **Optional configuration** - Leagues without rating don't need config
3. **ENUM defaults** - Model fields reference ENUMs, not magic numbers
4. **Versioning potential** - Can track config history if needed

### Model Definition

```python
class LeagueRatingConfig(models.Model):
    """Rating system configuration for a league.

    All defaults come from RatingDefaults enum. Leagues can customize
    any value by setting the corresponding field.
    """

    league = models.OneToOneField(
        "League",
        on_delete=models.CASCADE,
        related_name="rating_config",
    )

    # === Rating System Selection ===
    rating_system = models.CharField(
        max_length=20,
        choices=RatingSystem.choices(),
        default=RatingSystem.ELO.value,
        help_text="Which algorithm to use for rating calculations",
    )

    # === K-Factor Configuration ===
    k_factor_mode = models.CharField(
        max_length=20,
        choices=KFactorMode.choices(),
        default=KFactorMode.HYBRID.value,
        help_text="How K-factor is determined for each player",
    )
    k_factor_default = models.FloatField(
        default=RatingDefaults.K_FACTOR_DEFAULT.value,
        help_text="Standard K-factor for rating calculations",
    )
    k_factor_placement = models.FloatField(
        default=RatingDefaults.K_FACTOR_PLACEMENT.value,
        help_text="K-factor for players in placement games",
    )
    k_factor_bottom_percentile = models.FloatField(
        default=RatingDefaults.K_FACTOR_BOTTOM_PERCENTILE.value,
        help_text="K-factor for bottom percentile players (faster climb)",
    )
    k_factor_top_percentile = models.FloatField(
        default=RatingDefaults.K_FACTOR_TOP_PERCENTILE.value,
        help_text="K-factor for top percentile players (more stable)",
    )
    percentile_threshold = models.FloatField(
        default=RatingDefaults.PERCENTILE_THRESHOLD.value,
        help_text="Threshold for top/bottom percentile (e.g., 0.05 = 5%)",
    )

    # === Placement Configuration ===
    placement_games = models.PositiveIntegerField(
        default=int(RatingDefaults.PLACEMENT_GAMES.value),
        help_text="Number of games before using standard K-factor",
    )
    min_games_for_ranking = models.PositiveIntegerField(
        default=int(RatingDefaults.MIN_GAMES_FOR_RANKING.value),
        help_text="Minimum games to appear on leaderboard",
    )

    # === Fixed Delta Configuration ===
    fixed_delta_win = models.FloatField(
        default=RatingDefaults.FIXED_DELTA_WIN.value,
        help_text="Points gained on win (fixed_delta system)",
    )
    fixed_delta_loss = models.FloatField(
        default=RatingDefaults.FIXED_DELTA_LOSS.value,
        help_text="Points lost on loss (fixed_delta system)",
    )

    # === Age Decay Configuration ===
    age_decay_enabled = models.BooleanField(
        default=False,
        help_text="Whether to apply age decay to older matches",
    )
    age_decay_half_life_days = models.PositiveIntegerField(
        default=int(RatingDefaults.AGE_DECAY_HALF_LIFE_DAYS.value),
        help_text="Days until match counts for 50% weight",
    )
    age_decay_minimum = models.FloatField(
        default=RatingDefaults.AGE_DECAY_MINIMUM.value,
        help_text="Minimum weight for very old matches (0.0-1.0)",
    )

    # === Glicko-2 Configuration ===
    glicko_initial_rd = models.FloatField(
        default=RatingDefaults.GLICKO_INITIAL_RD.value,
        help_text="Initial rating deviation for new players",
    )
    glicko_initial_volatility = models.FloatField(
        default=RatingDefaults.GLICKO_INITIAL_VOLATILITY.value,
        help_text="Initial volatility for new players",
    )
    glicko_tau = models.FloatField(
        default=RatingDefaults.GLICKO_TAU.value,
        help_text="System constant (lower = less volatile ratings)",
    )
    glicko_rd_decay_per_day = models.FloatField(
        default=RatingDefaults.GLICKO_RD_DECAY_PER_DAY.value,
        help_text="RD increase per day of inactivity",
    )

    # === Recalculation Constraints ===
    recalc_max_age_days = models.PositiveIntegerField(
        default=int(RatingDefaults.RECALC_MAX_AGE_DAYS.value),
        help_text="Maximum age in days for match recalculation",
    )
    recalc_mmr_threshold = models.PositiveIntegerField(
        default=int(RatingDefaults.RECALC_MMR_THRESHOLD.value),
        help_text="Maximum MMR change allowed for recalculation",
    )

    # === MMR Epoch Configuration ===
    mmr_epoch_enabled = models.BooleanField(
        default=True,
        help_text="Reset rating when player MMR changes significantly",
    )
    mmr_epoch_threshold = models.PositiveIntegerField(
        default=int(RatingDefaults.MMR_EPOCH_THRESHOLD.value),
        help_text="MMR change that triggers a new epoch",
    )

    # === Display Configuration ===
    display_rating = models.CharField(
        max_length=20,
        choices=DisplayRating.choices(),
        default=DisplayRating.TOTAL_ELO.value,
        help_text="Which rating to show in UI by default",
    )
    show_uncertainty = models.BooleanField(
        default=True,
        help_text="Show rating deviation/uncertainty in popups",
    )

    # === Timestamps ===
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "League Rating Configuration"
        verbose_name_plural = "League Rating Configurations"

    def __str__(self):
        return f"Rating Config for {self.league.name}"

    @classmethod
    def get_or_create_for_league(cls, league):
        """Get config for league, creating with defaults if needed."""
        config, created = cls.objects.get_or_create(league=league)
        return config
```

---

## Section 3: Updated LeagueRating Model

### MMR Epochs

When a player's verified MMR changes significantly from their `base_mmr`, we start a new "epoch":

- Previous rating stats are zeroed
- New `base_mmr` is set to current MMR
- Match history is preserved but tagged with epoch
- This prevents old games at 1000 MMR from affecting a 5000 MMR player

```python
class LeagueRating(models.Model):
    """Per-player rating within a specific league."""

    league = models.ForeignKey(
        "League",
        on_delete=models.CASCADE,
        related_name="ratings",
    )
    player = models.ForeignKey(
        "CustomUser",
        on_delete=models.CASCADE,
        related_name="league_ratings",
    )

    # === Base MMR ===
    base_mmr = models.IntegerField(
        default=0,
        help_text="Player's Dota MMR when current epoch started",
    )
    base_mmr_snapshot_date = models.DateTimeField(
        auto_now_add=True,
        help_text="When base_mmr was captured",
    )

    # === Epoch Tracking ===
    epoch = models.PositiveIntegerField(
        default=1,
        help_text="Current rating epoch (increments on significant MMR change)",
    )
    epoch_started_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the current epoch began",
    )
    previous_epochs_data = models.JSONField(
        default=list,
        blank=True,
        help_text="Historical data from previous epochs",
    )

    # === Elo-style Rating ===
    positive_stats = models.FloatField(
        default=0.0,
        help_text="Accumulated positive rating changes in current epoch",
    )
    negative_stats = models.FloatField(
        default=0.0,
        help_text="Accumulated negative rating changes in current epoch",
    )

    # === Glicko-2 Rating ===
    glicko_rating = models.FloatField(
        default=1500.0,
        help_text="Glicko-2 rating (separate from Elo)",
    )
    rating_deviation = models.FloatField(
        default=350.0,
        help_text="Rating deviation (uncertainty) - decreases with games",
    )
    volatility = models.FloatField(
        default=0.06,
        help_text="Volatility - how consistent the player is",
    )
    rd_last_updated = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time RD was calculated (for inactivity decay)",
    )

    # === Statistics ===
    games_played = models.PositiveIntegerField(default=0)
    wins = models.PositiveIntegerField(default=0)
    losses = models.PositiveIntegerField(default=0)
    last_played = models.DateTimeField(null=True, blank=True)

    # === Timestamps ===
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["league", "player"]
        ordering = ["-positive_stats", "negative_stats"]

    # === Properties ===

    @property
    def total_elo(self) -> float:
        """Elo-style rating: base_mmr + positive - negative."""
        return self.base_mmr + self.positive_stats - self.negative_stats

    @property
    def net_change(self) -> float:
        """Net rating change in current epoch."""
        return self.positive_stats - self.negative_stats

    @property
    def win_rate(self) -> float:
        """Win percentage."""
        if self.games_played == 0:
            return 0.0
        return self.wins / self.games_played

    @property
    def is_placement(self) -> bool:
        """Whether player is still in placement games."""
        config = self.league.rating_config
        return self.games_played < config.placement_games

    @property
    def is_ranked(self) -> bool:
        """Whether player has enough games to be ranked."""
        config = self.league.rating_config
        return self.games_played >= config.min_games_for_ranking

    @property
    def glicko_confidence_interval(self) -> tuple:
        """95% confidence interval for Glicko rating."""
        margin = 1.96 * self.rating_deviation
        return (self.glicko_rating - margin, self.glicko_rating + margin)

    @property
    def display_rating(self) -> float:
        """Get the rating to display based on league config."""
        config = self.league.rating_config
        if config.display_rating == DisplayRating.NET_CHANGE.value:
            return self.net_change
        elif config.display_rating == DisplayRating.GLICKO_RATING.value:
            return self.glicko_rating
        return self.total_elo  # Default to total_elo

    # === Methods ===

    def check_epoch_change(self, new_mmr: int) -> bool:
        """Check if MMR changed enough to trigger new epoch."""
        config = self.league.rating_config
        if not config.mmr_epoch_enabled:
            return False
        return abs(new_mmr - self.base_mmr) > config.mmr_epoch_threshold

    def start_new_epoch(self, new_mmr: int):
        """
        Start a new rating epoch with fresh stats.

        Called when player's verified MMR changes significantly.
        Preserves history in previous_epochs_data.
        """
        from django.utils import timezone

        # Archive current epoch data
        epoch_data = {
            "epoch": self.epoch,
            "base_mmr": self.base_mmr,
            "positive_stats": self.positive_stats,
            "negative_stats": self.negative_stats,
            "total_elo": self.total_elo,
            "glicko_rating": self.glicko_rating,
            "rating_deviation": self.rating_deviation,
            "games_played": self.games_played,
            "wins": self.wins,
            "losses": self.losses,
            "started_at": self.epoch_started_at.isoformat(),
            "ended_at": timezone.now().isoformat(),
        }

        if self.previous_epochs_data is None:
            self.previous_epochs_data = []
        self.previous_epochs_data.append(epoch_data)

        # Reset for new epoch
        config = self.league.rating_config
        self.base_mmr = new_mmr
        self.base_mmr_snapshot_date = timezone.now()
        self.positive_stats = 0.0
        self.negative_stats = 0.0
        self.glicko_rating = 1500.0  # Glicko starts at 1500
        self.rating_deviation = config.glicko_initial_rd
        self.volatility = config.glicko_initial_volatility
        self.games_played = 0
        self.wins = 0
        self.losses = 0
        self.epoch += 1
        self.epoch_started_at = timezone.now()
        self.rd_last_updated = timezone.now()

        self.save()

    def update_rd_for_inactivity(self):
        """
        Increase rating deviation based on inactivity.

        Call this before calculating a match.
        """
        from django.utils import timezone

        if self.rd_last_updated is None:
            self.rd_last_updated = timezone.now()
            return

        config = self.league.rating_config
        days_inactive = (timezone.now() - self.rd_last_updated).days

        if days_inactive > 0:
            # RD increases with inactivity (more uncertainty)
            rd_increase = config.glicko_rd_decay_per_day * days_inactive
            self.rating_deviation = min(
                self.rating_deviation + rd_increase,
                RatingDefaults.GLICKO_RD_MAX.value
            )
            self.rd_last_updated = timezone.now()
```

---

## Section 4: K-Factor Modes

### Implementation

```python
class KFactorCalculator:
    """Calculate K-factor based on league configuration."""

    def __init__(self, config: "LeagueRatingConfig"):
        self.config = config

    def get_k_factor(self, rating: "LeagueRating") -> float:
        """Get K-factor for a player based on configured mode."""
        mode = self.config.k_factor_mode

        if mode == KFactorMode.FIXED.value:
            return self._fixed_k()
        elif mode == KFactorMode.PLACEMENT.value:
            return self._placement_k(rating)
        elif mode == KFactorMode.PERCENTILE.value:
            return self._percentile_k(rating)
        elif mode == KFactorMode.HYBRID.value:
            return self._hybrid_k(rating)
        else:
            return self.config.k_factor_default

    def _fixed_k(self) -> float:
        """Same K for everyone."""
        return self.config.k_factor_default

    def _placement_k(self, rating: "LeagueRating") -> float:
        """Higher K during placement games."""
        if rating.games_played < self.config.placement_games:
            return self.config.k_factor_placement
        return self.config.k_factor_default

    def _percentile_k(self, rating: "LeagueRating") -> float:
        """K based on league percentile ranking."""
        percentile = self._calculate_percentile(rating)
        threshold = self.config.percentile_threshold

        if percentile <= threshold:
            # Bottom percentile - higher K for faster climb
            return self.config.k_factor_bottom_percentile
        elif percentile >= (1 - threshold):
            # Top percentile - lower K for stability
            return self.config.k_factor_top_percentile
        return self.config.k_factor_default

    def _hybrid_k(self, rating: "LeagueRating") -> float:
        """Placement K first, then percentile-based."""
        if rating.games_played < self.config.placement_games:
            return self.config.k_factor_placement
        return self._percentile_k(rating)

    def _calculate_percentile(self, rating: "LeagueRating") -> float:
        """Calculate player's percentile rank in the league."""
        from app.models import LeagueRating

        league_ratings = LeagueRating.objects.filter(
            league=rating.league,
            games_played__gte=self.config.min_games_for_ranking,
        )
        total = league_ratings.count()

        if total <= 1:
            return 0.5  # Only player or no players

        # Count players with lower rating
        below = league_ratings.filter(
            total_elo__lt=rating.total_elo
        ).count()

        return below / (total - 1)
```

---

## Section 5: Glicko-2 Implementation

### Algorithm Overview

Glicko-2 improves on Elo by tracking:
1. **Rating (μ)** - skill estimate
2. **Rating Deviation (φ)** - uncertainty (decreases with games, increases with inactivity)
3. **Volatility (σ)** - consistency (high = erratic results)

### Implementation

```python
import math
from typing import List, Tuple


class Glicko2RatingSystem:
    """Full Glicko-2 implementation."""

    # Scale factor between Glicko-2 internal and display scales
    SCALE = 173.7178

    def __init__(self, config: "LeagueRatingConfig"):
        self.config = config
        self.tau = config.glicko_tau

    def calculate_match(
        self,
        winner_ratings: List["LeagueRating"],
        loser_ratings: List["LeagueRating"],
        age_decay_factor: float = 1.0,
    ) -> dict:
        """
        Calculate Glicko-2 updates for a team match.

        Returns dict with updates for each player.
        """
        # Use team average for team vs team
        winner_avg = self._team_average(winner_ratings)
        loser_avg = self._team_average(loser_ratings)

        results = {"winners": {}, "losers": {}}

        for rating in winner_ratings:
            new_r, new_rd, new_vol = self._update_rating(
                rating, opponent_avg=loser_avg, score=1.0, age_decay=age_decay_factor
            )
            results["winners"][rating.player_id] = {
                "new_rating": new_r,
                "new_rd": new_rd,
                "new_volatility": new_vol,
                "delta": new_r - rating.glicko_rating,
            }

        for rating in loser_ratings:
            new_r, new_rd, new_vol = self._update_rating(
                rating, opponent_avg=winner_avg, score=0.0, age_decay=age_decay_factor
            )
            results["losers"][rating.player_id] = {
                "new_rating": new_r,
                "new_rd": new_rd,
                "new_volatility": new_vol,
                "delta": new_r - rating.glicko_rating,
            }

        return results

    def _team_average(self, ratings: List["LeagueRating"]) -> Tuple[float, float]:
        """Get average rating and RD for a team."""
        if not ratings:
            return (1500.0, 350.0)

        avg_rating = sum(r.glicko_rating for r in ratings) / len(ratings)
        avg_rd = sum(r.rating_deviation for r in ratings) / len(ratings)
        return (avg_rating, avg_rd)

    def _update_rating(
        self,
        rating: "LeagueRating",
        opponent_avg: Tuple[float, float],
        score: float,
        age_decay: float = 1.0,
    ) -> Tuple[float, float, float]:
        """
        Update a single player's Glicko-2 rating.

        Returns (new_rating, new_rd, new_volatility)
        """
        # Convert to Glicko-2 scale
        mu = (rating.glicko_rating - 1500) / self.SCALE
        phi = rating.rating_deviation / self.SCALE
        sigma = rating.volatility

        opp_mu = (opponent_avg[0] - 1500) / self.SCALE
        opp_phi = opponent_avg[1] / self.SCALE

        # Step 3: Compute variance
        g_phi = self._g(opp_phi)
        E = self._E(mu, opp_mu, opp_phi)
        v = 1 / (g_phi**2 * E * (1 - E))

        # Step 4: Compute delta
        delta = v * g_phi * (score - E)

        # Apply age decay to delta
        delta *= age_decay

        # Step 5: Compute new volatility
        new_sigma = self._compute_volatility(sigma, phi, v, delta)

        # Step 6: Update RD
        phi_star = math.sqrt(phi**2 + new_sigma**2)

        # Step 7: Update rating and RD
        new_phi = 1 / math.sqrt(1/phi_star**2 + 1/v)
        new_mu = mu + new_phi**2 * g_phi * (score - E) * age_decay

        # Convert back to display scale
        new_rating = new_mu * self.SCALE + 1500
        new_rd = new_phi * self.SCALE

        # Enforce RD bounds
        new_rd = max(
            RatingDefaults.GLICKO_RD_MIN.value,
            min(new_rd, RatingDefaults.GLICKO_RD_MAX.value)
        )

        return (new_rating, new_rd, new_sigma)

    def _g(self, phi: float) -> float:
        """Glicko-2 g function."""
        return 1 / math.sqrt(1 + 3 * phi**2 / math.pi**2)

    def _E(self, mu: float, opp_mu: float, opp_phi: float) -> float:
        """Expected score function."""
        return 1 / (1 + math.exp(-self._g(opp_phi) * (mu - opp_mu)))

    def _compute_volatility(
        self, sigma: float, phi: float, v: float, delta: float
    ) -> float:
        """
        Compute new volatility using iterative algorithm.

        This is the Illinois algorithm for finding the root.
        """
        a = math.log(sigma**2)

        def f(x):
            ex = math.exp(x)
            d2 = delta**2
            p2 = phi**2
            return (
                ex * (d2 - p2 - v - ex) / (2 * (p2 + v + ex)**2)
                - (x - a) / self.tau**2
            )

        # Find bounds
        A = a
        if delta**2 > phi**2 + v:
            B = math.log(delta**2 - phi**2 - v)
        else:
            k = 1
            while f(a - k * self.tau) < 0:
                k += 1
            B = a - k * self.tau

        # Iterate
        fA = f(A)
        fB = f(B)

        while abs(B - A) > 0.000001:
            C = A + (A - B) * fA / (fB - fA)
            fC = f(C)

            if fC * fB < 0:
                A = B
                fA = fB
            else:
                fA /= 2

            B = C
            fB = fC

        return math.exp(A / 2)
```

---

## Section 6: Player Rating Popup

### API Response Schema

```python
# Serializer for player rating popup
class PlayerLeagueRatingSerializer(serializers.ModelSerializer):
    """Detailed rating info for player popup."""

    league_name = serializers.CharField(source='league.name')
    league_id = serializers.IntegerField(source='league.id')

    # Display rating based on league config
    display_rating = serializers.FloatField()
    display_system = serializers.SerializerMethodField()

    # Elo components
    base_mmr = serializers.IntegerField()
    rating_change = serializers.FloatField(source='net_change')
    total_elo = serializers.FloatField()

    # Glicko components (if applicable)
    glicko_rating = serializers.FloatField()
    rating_deviation = serializers.FloatField()
    volatility = serializers.FloatField()
    confidence_interval = serializers.SerializerMethodField()

    # Statistics
    games_played = serializers.IntegerField()
    wins = serializers.IntegerField()
    losses = serializers.IntegerField()
    win_rate = serializers.FloatField()

    # Status
    is_placement = serializers.BooleanField()
    is_ranked = serializers.BooleanField()

    # Epoch info
    epoch = serializers.IntegerField()
    epoch_started_at = serializers.DateTimeField()

    class Meta:
        model = LeagueRating
        fields = [
            'league_id', 'league_name',
            'display_rating', 'display_system',
            'base_mmr', 'rating_change', 'total_elo',
            'glicko_rating', 'rating_deviation', 'volatility', 'confidence_interval',
            'games_played', 'wins', 'losses', 'win_rate',
            'is_placement', 'is_ranked',
            'epoch', 'epoch_started_at',
        ]

    def get_display_system(self, obj):
        config = obj.league.rating_config
        if config.rating_system == RatingSystem.GLICKO2.value:
            return 'glicko'
        return 'elo'

    def get_confidence_interval(self, obj):
        low, high = obj.glicko_confidence_interval
        return {'low': round(low, 0), 'high': round(high, 0)}
```

### Frontend Component

```typescript
interface PlayerLeagueRating {
  leagueId: number;
  leagueName: string;

  displayRating: number;
  displaySystem: 'elo' | 'glicko';

  baseMmr: number;
  ratingChange: number;
  totalElo: number;

  glickoRating?: number;
  ratingDeviation?: number;
  volatility?: number;
  confidenceInterval?: { low: number; high: number };

  gamesPlayed: number;
  wins: number;
  losses: number;
  winRate: number;

  isPlacement: boolean;
  isRanked: boolean;

  epoch: number;
  epochStartedAt: string;
}

function PlayerRatingPopup({ rating }: { rating: PlayerLeagueRating }) {
  return (
    <div className="rating-popup">
      <h3>{rating.leagueName}</h3>

      {/* Main Rating Display */}
      <div className="rating-main">
        <span className="rating-value">{Math.round(rating.displayRating)}</span>
        <span className="rating-change">
          {rating.ratingChange >= 0 ? '+' : ''}{Math.round(rating.ratingChange)}
        </span>
      </div>

      {/* Glicko uncertainty (if enabled) */}
      {rating.displaySystem === 'glicko' && rating.confidenceInterval && (
        <div className="confidence-interval">
          95% CI: {rating.confidenceInterval.low} - {rating.confidenceInterval.high}
        </div>
      )}

      {/* Stats */}
      <div className="stats">
        <span>{rating.gamesPlayed} games</span>
        <span>{rating.wins}W / {rating.losses}L</span>
        <span>{(rating.winRate * 100).toFixed(1)}%</span>
      </div>

      {/* Status badges */}
      {rating.isPlacement && <span className="badge placement">Placement</span>}
      {!rating.isRanked && <span className="badge unranked">Unranked</span>}

      {/* Epoch info (if > 1) */}
      {rating.epoch > 1 && (
        <div className="epoch-info">
          Season {rating.epoch} (Base MMR: {rating.baseMmr})
        </div>
      )}
    </div>
  );
}
```

---

## Section 7: Match Finalization with Dual Rating

### Updated Service

When finalizing a match, we update BOTH Elo-style and Glicko-2 ratings:

```python
class LeagueMatchService:
    """Service for managing league matches and rating updates."""

    @classmethod
    @transaction.atomic
    def finalize(
        cls,
        match: "LeagueMatch",
        winners: List["CustomUser"],
        losers: List["CustomUser"],
        winning_side: str,
    ):
        """
        Finalize a match and update all participant ratings.

        Updates both Elo-style ratings (positive/negative stats)
        AND Glicko-2 ratings based on league configuration.
        """
        if match.is_finalized:
            raise ValueError("Match is already finalized")

        league = match.league
        config = LeagueRatingConfig.get_or_create_for_league(league)

        # Get age decay
        age_decay = cls._calculate_age_decay(config, match.played_at)

        # Get or create ratings for all players
        winner_ratings = cls._get_or_create_ratings(league, winners)
        loser_ratings = cls._get_or_create_ratings(league, losers)

        # Lock ratings to prevent race conditions
        all_ratings = winner_ratings + loser_ratings
        LeagueRating.objects.filter(
            pk__in=[r.pk for r in all_ratings]
        ).select_for_update()

        # Update RD for inactivity (Glicko-2)
        for rating in all_ratings:
            rating.update_rd_for_inactivity()

        # === Calculate Elo-style deltas ===
        k_calc = KFactorCalculator(config)
        elo_system = cls._get_elo_system(config)
        elo_result = elo_system.calculate_team_deltas(
            winner_ratings, loser_ratings, age_decay
        )

        # === Calculate Glicko-2 deltas ===
        glicko_system = Glicko2RatingSystem(config)
        glicko_result = glicko_system.calculate_match(
            winner_ratings, loser_ratings, age_decay
        )

        # === Apply updates and create participants ===
        for rating, is_winner in [
            *[(r, True) for r in winner_ratings],
            *[(r, False) for r in loser_ratings],
        ]:
            player_id = rating.player_id
            elo_before = rating.total_elo

            # Get deltas
            if is_winner:
                elo_delta = elo_result["winner_delta"]
                k_used = elo_result["winner_k_factors"].get(player_id, config.k_factor_default)
                glicko_updates = glicko_result["winners"].get(player_id, {})
            else:
                elo_delta = -elo_result["loser_delta"]  # Negative for losers
                k_used = elo_result["loser_k_factors"].get(player_id, config.k_factor_default)
                glicko_updates = glicko_result["losers"].get(player_id, {})

            # Update Elo-style stats
            if elo_delta >= 0:
                rating.positive_stats += elo_delta
            else:
                rating.negative_stats += abs(elo_delta)

            # Update Glicko-2 stats
            if glicko_updates:
                rating.glicko_rating = glicko_updates["new_rating"]
                rating.rating_deviation = glicko_updates["new_rd"]
                rating.volatility = glicko_updates["new_volatility"]
                rating.rd_last_updated = timezone.now()

            # Update game stats
            rating.games_played += 1
            if is_winner:
                rating.wins += 1
            else:
                rating.losses += 1
            rating.last_played = match.played_at

            rating.save()

            # Create participant record
            LeagueMatchParticipant.objects.create(
                match=match,
                player=rating.player,
                player_rating=rating,
                team_side=winning_side if is_winner else ("dire" if winning_side == "radiant" else "radiant"),
                mmr_at_match=rating.base_mmr,
                elo_before=elo_before,
                elo_after=rating.total_elo,
                k_factor_used=k_used,
                rating_deviation_used=rating.rating_deviation,
                age_decay_factor=age_decay,
                is_winner=is_winner,
                delta=elo_delta,
                # New Glicko fields
                glicko_before=elo_before,  # Store old glicko
                glicko_after=rating.glicko_rating,
                glicko_delta=glicko_updates.get("delta", 0),
            )

        # Mark match as finalized
        match.is_finalized = True
        match.finalized_at = timezone.now()
        match.save()
```

---

## Section 8: Migration Path

### Phase 1: Create LeagueRatingConfig

1. Create `LeagueRatingConfig` model
2. Create migration
3. Move existing League rating fields to config
4. Create configs for existing leagues with current values

### Phase 2: Update LeagueRating

1. Add epoch tracking fields
2. Add Glicko-2 fields (some already exist)
3. Create migration

### Phase 3: Update Services

1. Update `KFactorCalculator` with all modes
2. Implement `Glicko2RatingSystem`
3. Update `LeagueMatchService.finalize()`

### Phase 4: API & Frontend

1. Add `PlayerLeagueRatingSerializer`
2. Add API endpoint for player ratings
3. Create rating popup component
4. Update leaderboard to use new config

---

## Summary of Changes from v1

| Aspect | v1 Design | v2 Design |
|--------|-----------|-----------|
| **Config location** | Fields on League model | Separate LeagueRatingConfig model |
| **Defaults** | Hardcoded in model fields | ENUMs in constants.py |
| **K-factor** | Percentile only | Placement, Percentile, Fixed, Hybrid |
| **MMR changes** | Not handled | Epoch system resets on significant change |
| **Glicko-2** | Fields only | Full implementation |
| **Display** | Single rating | Configurable (Elo/Glicko/Net Change) |
| **Player popup** | Not defined | Full spec with uncertainty display |
