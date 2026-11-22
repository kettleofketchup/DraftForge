from django.db import models


class LeagueRating(models.Model):
    """Per-player rating within a specific league."""

    league = models.ForeignKey(
        "league.League",
        on_delete=models.CASCADE,
        related_name="ratings",
    )
    player = models.ForeignKey(
        "app.CustomUser",
        on_delete=models.CASCADE,
        related_name="league_ratings",
    )

    base_mmr = models.IntegerField(
        default=0,
        help_text="Player's MMR when joining the league",
    )

    # Separate positive and negative stats for flexibility
    positive_stats = models.FloatField(
        default=0.0,
        help_text="Accumulated positive rating changes (wins)",
    )
    negative_stats = models.FloatField(
        default=0.0,
        help_text="Accumulated negative rating changes (losses)",
    )

    # Glicko-2 support (for future use)
    rating_deviation = models.FloatField(
        default=350.0,
        help_text="Rating deviation (uncertainty) for Glicko-2",
    )
    volatility = models.FloatField(
        default=0.06,
        help_text="Volatility for Glicko-2",
    )

    # Tracking
    games_played = models.PositiveIntegerField(default=0)
    wins = models.PositiveIntegerField(default=0)
    losses = models.PositiveIntegerField(default=0)
    last_played = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "app_leaguerating"
        unique_together = ["league", "player"]
        ordering = ["-positive_stats", "negative_stats"]
        verbose_name = "League Rating"
        verbose_name_plural = "League Ratings"

    @property
    def total_elo(self) -> float:
        """Calculate total Elo as base_mmr + positive_stats - negative_stats."""
        return self.base_mmr + self.positive_stats - self.negative_stats

    @property
    def net_change(self) -> float:
        """Net rating change since joining the league."""
        return self.positive_stats - self.negative_stats

    def __str__(self) -> str:
        return f"{self.player.username} in {self.league.name}: {self.total_elo:.0f}"


class LeagueMatch(models.Model):
    """A recorded match within a league for rating purposes."""

    league = models.ForeignKey(
        "league.League",
        on_delete=models.CASCADE,
        related_name="matches",
    )
    game = models.OneToOneField(
        "app.Game",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="league_match",
        help_text="Link to Game model if applicable",
    )

    # Match metadata
    played_at = models.DateTimeField(
        help_text="When the match was played",
    )
    stage = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Tournament stage (e.g., 'quarterfinal', 'grand_final')",
    )
    bracket_slot = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        help_text="Bracket position identifier",
    )

    # Finalization tracking
    is_finalized = models.BooleanField(
        default=False,
        help_text="Whether ratings have been calculated",
    )
    finalized_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When ratings were calculated",
    )

    # Recalculation tracking
    recalculation_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of times this match has been recalculated",
    )
    last_recalculated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When ratings were last recalculated",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "app_leaguematch"
        ordering = ["-played_at"]
        verbose_name = "League Match"
        verbose_name_plural = "League Matches"

    def __str__(self) -> str:
        status = "finalized" if self.is_finalized else "pending"
        return f"Match {self.pk} in {self.league.name} ({status})"


class LeagueMatchParticipant(models.Model):
    """A player's participation in a league match."""

    TEAM_SIDE_CHOICES = [
        ("radiant", "Radiant"),
        ("dire", "Dire"),
    ]

    match = models.ForeignKey(
        "league.LeagueMatch",
        on_delete=models.CASCADE,
        related_name="participants",
    )
    player = models.ForeignKey(
        "app.CustomUser",
        on_delete=models.CASCADE,
        related_name="league_match_participations",
    )
    player_rating = models.ForeignKey(
        "league.LeagueRating",
        on_delete=models.CASCADE,
        related_name="match_participations",
    )

    # Team info
    team_side = models.CharField(
        max_length=8,
        choices=TEAM_SIDE_CHOICES,
    )

    # Snapshot at match time
    mmr_at_match = models.IntegerField(
        help_text="Player's base MMR at time of match",
    )
    elo_before = models.FloatField(
        help_text="Player's total Elo before this match",
    )
    elo_after = models.FloatField(
        help_text="Player's total Elo after this match",
    )

    # Rating calculation factors
    k_factor_used = models.FloatField(
        help_text="K-factor used in calculation",
    )
    rating_deviation_used = models.FloatField(
        default=350.0,
        help_text="Rating deviation at time of calculation",
    )
    age_decay_factor = models.FloatField(
        default=1.0,
        help_text="Age decay factor applied (1.0 = no decay)",
    )

    # Result
    is_winner = models.BooleanField()
    delta = models.FloatField(
        help_text="Rating change from this match",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "app_leaguematchparticipant"
        unique_together = ["match", "player"]
        ordering = ["team_side", "player__username"]
        verbose_name = "League Match Participant"
        verbose_name_plural = "League Match Participants"

    def __str__(self) -> str:
        result = "W" if self.is_winner else "L"
        return f"{self.player.username} ({result}) in Match {self.match_id}"
