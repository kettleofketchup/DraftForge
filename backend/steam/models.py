import logging

from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


class Match(models.Model):
    match_id = models.BigIntegerField(primary_key=True)
    radiant_win = models.BooleanField()
    duration = models.IntegerField()
    start_time = models.IntegerField()
    game_mode = models.IntegerField()
    lobby_type = models.IntegerField()
    league_id = models.IntegerField(null=True, blank=True, db_index=True)

    def __str__(self):
        return str(self.match_id)


class PlayerMatchStats(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="players")
    steam_id = models.BigIntegerField()
    user = models.ForeignKey(
        "app.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="match_stats",
    )
    player_slot = models.IntegerField()
    hero_id = models.IntegerField()
    kills = models.IntegerField()
    deaths = models.IntegerField()
    assists = models.IntegerField()
    gold_per_min = models.IntegerField()
    xp_per_min = models.IntegerField()
    last_hits = models.IntegerField()
    denies = models.IntegerField()
    hero_damage = models.IntegerField()
    tower_damage = models.IntegerField()
    hero_healing = models.IntegerField()

    class Meta:
        unique_together = ("match", "steam_id")

    def __str__(self):
        return f"Match {self.match.match_id} - Player {self.steam_id}"


class LeagueSyncState(models.Model):
    league_id = models.IntegerField(unique=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_match_id = models.BigIntegerField(null=True, blank=True)
    failed_match_ids = models.JSONField(default=list)
    is_syncing = models.BooleanField(default=False)

    def __str__(self):
        return f"League {self.league_id} sync state"


class LeaguePlayerStats(models.Model):
    """Aggregated player statistics for a specific league."""

    user = models.ForeignKey(
        "app.CustomUser",
        on_delete=models.CASCADE,
        related_name="league_stats",
    )
    league_id = models.IntegerField(db_index=True)

    # Core stats
    games_played = models.IntegerField(default=0)
    wins = models.IntegerField(default=0)
    losses = models.IntegerField(default=0)

    # Aggregated performance (totals for averaging)
    total_kills = models.IntegerField(default=0)
    total_deaths = models.IntegerField(default=0)
    total_assists = models.IntegerField(default=0)
    total_gpm = models.IntegerField(default=0)
    total_xpm = models.IntegerField(default=0)

    # Cached calculations (updated on each match)
    win_rate = models.FloatField(default=0.0)
    avg_kills = models.FloatField(default=0.0)
    avg_deaths = models.FloatField(default=0.0)
    avg_assists = models.FloatField(default=0.0)
    avg_gpm = models.FloatField(default=0.0)
    avg_xpm = models.FloatField(default=0.0)

    # MMR adjustment calculated from performance
    mmr_adjustment = models.IntegerField(default=0)

    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "league_id")

    def __str__(self):
        return f"{self.user.username} - League {self.league_id} ({self.games_played} games)"

    def recalculate_averages(self):
        """Recalculate cached average fields from totals."""
        if self.games_played > 0:
            self.win_rate = self.wins / self.games_played
            self.avg_kills = self.total_kills / self.games_played
            self.avg_deaths = self.total_deaths / self.games_played
            self.avg_assists = self.total_assists / self.games_played
            self.avg_gpm = self.total_gpm / self.games_played
            self.avg_xpm = self.total_xpm / self.games_played
        else:
            self.win_rate = 0.0
            self.avg_kills = 0.0
            self.avg_deaths = 0.0
            self.avg_assists = 0.0
            self.avg_gpm = 0.0
            self.avg_xpm = 0.0


class GameMatchSuggestion(models.Model):
    game = models.ForeignKey(
        "app.Game",
        on_delete=models.CASCADE,
        related_name="match_suggestions",
    )
    match = models.ForeignKey(
        Match,
        on_delete=models.CASCADE,
        related_name="game_suggestions",
    )
    tournament = models.ForeignKey(
        "app.Tournament",
        on_delete=models.CASCADE,
        related_name="match_suggestions",
    )
    confidence_score = models.FloatField()
    player_overlap = models.IntegerField()
    auto_linked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("game", "match")

    def __str__(self):
        return f"Game {self.game_id} -> Match {self.match_id} ({self.confidence_score:.0%})"


@receiver(post_save, sender=Match)
def invalidate_game_cache_on_match_save(sender, instance, **kwargs):
    """
    Invalidate Game cache when a Steam Match is created or updated.
    This ensures bracket data stays fresh when match details change.
    """
    try:
        from cacheops import invalidate_model, invalidate_obj

        # Import Game here to avoid circular imports
        from app.models import Game

        # Find any Game objects linked to this match via gameid
        linked_games = Game.objects.filter(gameid=instance.match_id)
        for game in linked_games:
            invalidate_obj(game)
            logger.debug(
                f"Invalidated cache for Game {game.pk} linked to Match {instance.match_id}"
            )

        # Also invalidate the tournament cache if games were found
        if linked_games.exists():
            from app.models import Tournament

            tournament_ids = linked_games.values_list(
                "tournament_id", flat=True
            ).distinct()
            for tournament_id in tournament_ids:
                try:
                    tournament = Tournament.objects.get(pk=tournament_id)
                    invalidate_obj(tournament)
                    logger.debug(f"Invalidated cache for Tournament {tournament_id}")
                except Tournament.DoesNotExist:
                    pass
    except ImportError:
        # cacheops not installed or not configured
        pass
    except Exception as e:
        logger.warning(f"Failed to invalidate cache for Match {instance.match_id}: {e}")
