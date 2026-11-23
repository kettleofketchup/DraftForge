from typing import TYPE_CHECKING

from django.db import models

from app.cache_utils import invalidate_obj

if TYPE_CHECKING:
    from tournament.models.team import Team


class Game(models.Model):
    tournament = models.ForeignKey(
        "tournament.Tournament",
        related_name="games",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    league = models.ForeignKey(
        "league.League",
        related_name="games",
        on_delete=models.CASCADE,
        null=True,
        blank=True,  # Games can belong directly to a league
    )
    round = models.IntegerField(default=1)

    # Bracket positioning fields
    bracket_type = models.CharField(
        max_length=20,
        choices=[
            ("winners", "Winners Bracket"),
            ("losers", "Losers Bracket"),
            ("grand_finals", "Grand Finals"),
            ("swiss", "Swiss"),
        ],
        default="winners",
    )
    elimination_type = models.CharField(
        max_length=10,
        choices=[
            ("single", "Single Elimination"),
            ("double", "Double Elimination"),
            ("swiss", "Swiss"),
        ],
        default="double",
        help_text="single=loser out, double=loser drops to losers bracket, swiss=record-based",
    )
    position = models.IntegerField(
        default=0, help_text="Position within round (0-indexed)"
    )

    # Match flow - which game winner advances to
    next_game = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="source_games",
    )
    next_game_slot = models.CharField(
        max_length=10,
        choices=[("radiant", "Radiant"), ("dire", "Dire")],
        null=True,
        blank=True,
    )

    # Loser path (for double elimination)
    loser_next_game = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="loser_source_games",
        help_text="Game where loser advances to (for double elim rounds)",
    )
    loser_next_game_slot = models.CharField(
        max_length=10,
        choices=[("radiant", "Radiant"), ("dire", "Dire")],
        null=True,
        blank=True,
    )

    # Swiss format tracking
    swiss_record_wins = models.IntegerField(
        default=0, help_text="Team's wins entering this match (Swiss format)"
    )
    swiss_record_losses = models.IntegerField(
        default=0, help_text="Team's losses entering this match (Swiss format)"
    )

    # Match status
    status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("live", "Live"),
            ("completed", "Completed"),
        ],
        default="pending",
    )

    # Steam match ID if it exists (64-bit)
    gameid = models.BigIntegerField(null=True, blank=True)

    radiant_team = models.ForeignKey(
        "tournament.Team",
        related_name="games_as_radiant",
        null=True,
        on_delete=models.CASCADE,
        blank=True,
    )
    dire_team = models.ForeignKey(
        "tournament.Team",
        related_name="games_as_dire",
        null=True,
        on_delete=models.CASCADE,
        blank=True,
    )
    winning_team = models.ForeignKey(
        "tournament.Team",
        related_name="games_won",
        null=True,
        on_delete=models.CASCADE,
        blank=True,
    )

    def __str__(self) -> str:
        tourn_name = self.tournament.name if self.tournament else "No Tournament"
        radiant = self.radiant_team.name if self.radiant_team else "TBD"
        dire = self.dire_team.name if self.dire_team else "TBD"
        return f"{radiant} vs {dire} in {tourn_name}"

    @property
    def teams(self) -> "list[Team | None]":
        return [self.radiant_team, self.dire_team]

    class Meta:
        db_table = "app_game"
        indexes = [
            models.Index(fields=["tournament"]),
            models.Index(fields=["league"]),
            models.Index(fields=["status"]),
            models.Index(fields=["gameid"]),
            models.Index(fields=["radiant_team"]),
            models.Index(fields=["dire_team"]),
        ]

    def save(self, *args: object, **kwargs: object) -> None:
        super().save(*args, **kwargs)
        # Self-invalidation via cacheops post_save signal. Explicit
        # cascade keeps the tournament/league cached team lists fresh.
        if self.tournament_id:
            invalidate_obj(self.tournament)
        if self.league_id:
            invalidate_obj(self.league)
