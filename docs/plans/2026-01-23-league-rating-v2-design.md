# League Rating System v2 Design

## Implementation Status

### Completed
- [x] **Task 1**: Create RatingDefaults, KFactorMode, RatingSystem ENUMs (`app/leagues/constants.py`)
- [x] **Task 2**: Create LeagueRatingConfig model (`app/models.py`)
- [x] **Task 3**: Update LeagueRating model with epoch and Glicko-2 fields (`app/models.py`)
- [x] **Task 4**: Implement KFactorCalculator with all 4 modes (`app/leagues/k_factor.py`)
- [x] **Task 5**: Implement Glicko2RatingSystem (`app/leagues/glicko2.py`)
- [x] **Task 6**: Update LeagueMatchService for dual rating (`app/services/match_finalization.py`)
  - Added Glicko-2 tracking fields to LeagueMatchParticipant
  - Updated rating.py to use LeagueRatingConfig and KFactorCalculator
  - Updated match_finalization.py to update both Elo and Glicko-2 ratings
  - Updated calculate_age_decay to use LeagueRatingConfig values
<a href="https://github.com/yourusername/yourrepo/stargazers">
  <img src="https://img.shields.io/github/stars/kettleofketchup/dota_tournament?style=social" alt="Star on GitHub">
</a>

<script async defer src="https://buttons.github.io/buttons.js"></script>
<a class="github-button" href="https://github.com/kettleofketchup/dota_tournament" data-show-count="true" aria-label="Star yourusername/yourrepo on GitHub">Star</a>

### In Progremss
- [ ] **Task 7**: Organization-level rating aggregation (NEW - see Section 9)

### Remaining
- [ ] **Task 8**: Add PlayerLeagueRatingSerializer for API
- [ ] **Task 9**: Add API endpoint for player ratings
- [ ] **Task 10**: Create rating popup component (frontend)
- [ ] **Task 11**: Update leaderboard to use new config
- [ ] **Task 12**: MMR epoch auto-detection on verification update
- [ ] **Task 13**: RD inactivity decay scheduled task

### Files Changed
| File | Changes |
|------|---------|
| `app/leagues/__init__.py` | Package exports |
| `app/leagues/constants.py` | ENUMs: RatingSystem, KFactorMode, RatingDefaults, DisplayRating |
| `app/leagues/k_factor.py` | KFactorCalculator with FIXED, PLACEMENT, PERCENTILE, HYBRID modes |
| `app/leagues/glicko2.py` | Full Glicko-2 implementation for team matches |
| `app/models.py` | LeagueRatingConfig model, LeagueRating epoch/Glicko fields, LeagueMatchParticipant Glicko fields |
| `app/services/rating.py` | Updated to use LeagueRatingConfig and KFactorCalculator |
| `app/services/match_finalization.py` | Dual rating updates (Elo + Glicko-2), config-based age decay |
| `app/migrations/0064_*.py` | LeagueRatingConfig model |
| `app/migrations/0065_*.py` | LeagueRating epoch/Glicko fields |
| `app/migrations/0066_*.py` | LeagueMatchParticipant Glicko tracking fields |

---

## Overview

This document supersedes the original `2026-01-21-league-rating-design.md` with a more comprehensive design that includes:

- **LeagueRatingConfig** as a separate model with ENUM-based defaults
- **Multiple K-factor modes**: placement, percentile, fixed, and hybrid
- **MMR Epoch system** to handle significant MMR changes
- **Full Glicko-2 implementation**
- **Player popup** displaying rating details per league configuration
- **Organization-level rating** aggregation across multiple leagues (NEW)

---

## Core Problem: MMR Anchoring

**Scenario**: Player joins league with 1000 MMR, plays 10 games over a year, accumulates +200 rating. Their MMR is now 5000 (they improved IRL). Should those +200 points from playing against 1000 MMR opponents count toward their 5000 MMR rating?

**Answer**: No. When a player's verified MMR changes significantly, we start a new "epoch" - their old rating deltas no longer apply to their new skill level.

---

## Section 9: Organization-Level Rating Aggregation (NEW)

### Problem Statement

Organizations may run many small leagues:
- Weekly tournaments (8-16 players, ~8 matches)
- Monthly seasons (20-50 players, ~50 matches)
- Special events (varies)

Individual leagues may have insufficient data for accurate ratings. A player with 3 games in one league has high uncertainty. But if they've played 50 games across 10 leagues in the organization, we have much more data.

### Solution: OrganizationRating

Aggregate ratings across all leagues within an organization for a more accurate player skill estimate.

### Model Definition

```python
class OrganizationRating(models.Model):
    """Aggregated rating across all leagues in an organization.

    Combines data from multiple small leagues to provide more
    accurate skill estimates for organizations with many leagues.
    """

    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="player_ratings",
    )
    player = models.ForeignKey(
        "CustomUser",
        on_delete=models.CASCADE,
        related_name="organization_ratings",
    )

    # === Aggregated Elo-style Rating ===
    base_mmr = models.IntegerField(
        default=0,
        help_text="Player's current verified MMR",
    )
    positive_stats = models.FloatField(
        default=0.0,
        help_text="Sum of positive changes across all org leagues",
    )
    negative_stats = models.FloatField(
        default=0.0,
        help_text="Sum of negative changes across all org leagues",
    )

    # === Aggregated Glicko-2 Rating ===
    glicko_rating = models.FloatField(
        default=1500.0,
        help_text="Combined Glicko-2 rating across all org leagues",
    )
    rating_deviation = models.FloatField(
        default=350.0,
        help_text="Combined rating deviation (lower = more confident)",
    )
    volatility = models.FloatField(
        default=0.06,
        help_text="Combined volatility",
    )

    # === Statistics ===
    total_games = models.PositiveIntegerField(default=0)
    total_wins = models.PositiveIntegerField(default=0)
    total_losses = models.PositiveIntegerField(default=0)
    leagues_participated = models.PositiveIntegerField(
        default=0,
        help_text="Number of distinct leagues with games",
    )

    # === Timestamps ===
    last_played = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["organization", "player"]
        ordering = ["-glicko_rating", "rating_deviation"]
        verbose_name = "Organization Rating"
        verbose_name_plural = "Organization Ratings"

    @property
    def total_elo(self) -> float:
        """Aggregated Elo-style rating."""
        return self.base_mmr + self.positive_stats - self.negative_stats

    @property
    def net_change(self) -> float:
        """Net rating change across all leagues."""
        return self.positive_stats - self.negative_stats

    @property
    def win_rate(self) -> float:
        """Win percentage across all leagues."""
        if self.total_games == 0:
            return 0.0
        return self.total_wins / self.total_games

    @property
    def is_reliable(self) -> bool:
        """Whether we have enough data for reliable rating.

        True if either:
        - 10+ games total across org
        - 3+ games in 3+ different leagues
        """
        return self.total_games >= 10 or (
            self.leagues_participated >= 3 and self.total_games >= 9
        )
```

### Configuration: OrganizationRatingConfig

```python
class OrganizationRatingConfig(models.Model):
    """Configuration for organization-wide rating aggregation."""

    organization = models.OneToOneField(
        "Organization",
        on_delete=models.CASCADE,
        related_name="rating_config",
    )

    # === Aggregation Settings ===
    aggregation_enabled = models.BooleanField(
        default=True,
        help_text="Enable organization-wide rating aggregation",
    )
    aggregation_method = models.CharField(
        max_length=20,
        choices=[
            ("weighted_average", "Weighted Average"),
            ("bayesian", "Bayesian Combination"),
            ("most_recent", "Most Recent League"),
        ],
        default="weighted_average",
        help_text="How to combine ratings from multiple leagues",
    )

    # === Weighting ===
    weight_by_games = models.BooleanField(
        default=True,
        help_text="Weight league contributions by games played",
    )
    weight_by_recency = models.BooleanField(
        default=True,
        help_text="Weight recent leagues more heavily",
    )
    recency_half_life_days = models.PositiveIntegerField(
        default=90,
        help_text="Half-life for recency weighting",
    )

    # === Display ===
    show_org_rating_on_profile = models.BooleanField(
        default=True,
        help_text="Show organization rating on player profiles",
    )
    show_league_breakdown = models.BooleanField(
        default=True,
        help_text="Show per-league breakdown in popup",
    )

    # === Minimum Requirements ===
    min_games_for_ranking = models.PositiveIntegerField(
        default=5,
        help_text="Minimum org-wide games to appear on leaderboard",
    )
    min_leagues_for_reliable = models.PositiveIntegerField(
        default=2,
        help_text="Minimum leagues for 'reliable' badge",
    )
```

### Aggregation Service

```python
class OrganizationRatingService:
    """Service for calculating organization-wide ratings."""

    @classmethod
    def recalculate_for_player(cls, organization, player):
        """Recalculate org rating from all league ratings."""
        from app.models import LeagueRating, OrganizationRating

        # Get all league ratings for this player in this org
        league_ratings = LeagueRating.objects.filter(
            league__organization=organization,
            player=player,
            games_played__gt=0,
        ).select_related('league')

        if not league_ratings.exists():
            # Remove org rating if no league data
            OrganizationRating.objects.filter(
                organization=organization,
                player=player,
            ).delete()
            return None

        config = cls._get_config(organization)

        # Calculate aggregated values
        if config.aggregation_method == "weighted_average":
            result = cls._weighted_average(league_ratings, config)
        elif config.aggregation_method == "bayesian":
            result = cls._bayesian_combination(league_ratings, config)
        else:  # most_recent
            result = cls._most_recent(league_ratings)

        # Create or update org rating
        org_rating, _ = OrganizationRating.objects.update_or_create(
            organization=organization,
            player=player,
            defaults=result,
        )

        return org_rating

    @classmethod
    def _weighted_average(cls, league_ratings, config):
        """Calculate weighted average across leagues."""
        from django.utils import timezone

        total_weight = 0
        weighted_elo = 0
        weighted_glicko = 0
        weighted_rd_inv = 0  # Weight by inverse RD (more certain = more weight)

        total_games = 0
        total_wins = 0
        total_losses = 0
        total_positive = 0
        total_negative = 0
        last_played = None

        for rating in league_ratings:
            # Calculate weight
            weight = 1.0

            if config.weight_by_games:
                weight *= rating.games_played

            if config.weight_by_recency and rating.last_played:
                days_ago = (timezone.now() - rating.last_played).days
                recency_weight = 0.5 ** (days_ago / config.recency_half_life_days)
                weight *= recency_weight

            # Glicko weight by certainty (inverse RD)
            rd_weight = 1 / (rating.rating_deviation ** 2)

            total_weight += weight
            weighted_elo += weight * rating.total_elo
            weighted_glicko += rd_weight * rating.glicko_rating
            weighted_rd_inv += rd_weight

            total_games += rating.games_played
            total_wins += rating.wins
            total_losses += rating.losses
            total_positive += rating.positive_stats
            total_negative += rating.negative_stats

            if last_played is None or (rating.last_played and rating.last_played > last_played):
                last_played = rating.last_played

        # Calculate averages
        avg_elo = weighted_elo / total_weight if total_weight > 0 else 0
        avg_glicko = weighted_glicko / weighted_rd_inv if weighted_rd_inv > 0 else 1500
        combined_rd = 1 / (weighted_rd_inv ** 0.5) if weighted_rd_inv > 0 else 350

        # Get base MMR from most recent rating
        most_recent = max(league_ratings, key=lambda r: r.last_played or timezone.now())

        return {
            'base_mmr': most_recent.base_mmr,
            'positive_stats': total_positive,
            'negative_stats': total_negative,
            'glicko_rating': avg_glicko,
            'rating_deviation': combined_rd,
            'volatility': 0.06,  # Reset to default for combined
            'total_games': total_games,
            'total_wins': total_wins,
            'total_losses': total_losses,
            'leagues_participated': len(league_ratings),
            'last_played': last_played,
        }

    @classmethod
    def _bayesian_combination(cls, league_ratings, config):
        """Bayesian combination of Glicko ratings.

        Treats each league rating as a noisy observation of true skill.
        Combines using precision weighting (inverse variance).
        """
        # Similar to weighted_average but uses proper Bayesian update
        # This gives more weight to ratings with low RD (high confidence)
        # Implementation similar to above but with Bayesian formula
        pass  # TODO: Implement

    @classmethod
    def _most_recent(cls, league_ratings):
        """Use rating from most recently played league."""
        from django.utils import timezone

        most_recent = max(
            league_ratings,
            key=lambda r: r.last_played or timezone.datetime.min.replace(tzinfo=timezone.utc)
        )

        # Aggregate stats but use most recent league's rating
        total_games = sum(r.games_played for r in league_ratings)
        total_wins = sum(r.wins for r in league_ratings)
        total_losses = sum(r.losses for r in league_ratings)

        return {
            'base_mmr': most_recent.base_mmr,
            'positive_stats': sum(r.positive_stats for r in league_ratings),
            'negative_stats': sum(r.negative_stats for r in league_ratings),
            'glicko_rating': most_recent.glicko_rating,
            'rating_deviation': most_recent.rating_deviation,
            'volatility': most_recent.volatility,
            'total_games': total_games,
            'total_wins': total_wins,
            'total_losses': total_losses,
            'leagues_participated': len(league_ratings),
            'last_played': most_recent.last_played,
        }

    @classmethod
    def update_after_match(cls, match):
        """Update org ratings for all participants after a match."""
        organization = match.league.organization

        for participant in match.participants.all():
            cls.recalculate_for_player(organization, participant.player)
```

### Integration with Match Finalization

Add to `LeagueMatchService.finalize()`:

```python
# At the end of finalize(), after marking match as finalized:

# Update organization ratings for all participants
from app.services.organization_rating import OrganizationRatingService

for player in winners + losers:
    OrganizationRatingService.recalculate_for_player(league.organization, player)
```

### API Endpoint

```python
@api_view(['GET'])
def player_organization_rating(request, org_id, player_id):
    """Get player's organization-wide rating with league breakdown."""
    org_rating = get_object_or_404(
        OrganizationRating,
        organization_id=org_id,
        player_id=player_id,
    )

    league_ratings = LeagueRating.objects.filter(
        league__organization_id=org_id,
        player_id=player_id,
        games_played__gt=0,
    ).select_related('league')

    return Response({
        'organization_rating': OrganizationRatingSerializer(org_rating).data,
        'league_breakdown': LeagueRatingSerializer(league_ratings, many=True).data,
    })
```

### Use Cases

1. **Small Weekly Leagues**: Organization runs 8-player weekly tournaments. Each has only ~8 matches. Individual league ratings are unreliable, but combined org rating is accurate.

2. **Seasonal Leagues**: Organization has Spring, Summer, Fall leagues. Player plays 20 games each. Org rating combines all 60 games.

3. **Mixed Formats**: Organization runs both 1v1 and 5v5 leagues. Org rating aggregates all to show overall skill.

4. **Cross-League Rankings**: Organization leaderboard shows org rating, not individual league ratings.

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

## Section 4-8: [Previous sections remain unchanged]

See original document for K-Factor Modes, Glicko-2 Implementation, Player Rating Popup, Match Finalization, and Migration Path sections.

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
| **Organization rating** | Not supported | NEW: Aggregation across leagues |
