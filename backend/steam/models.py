from django.db import models


class Match(models.Model):
    match_id = models.BigIntegerField(primary_key=True)
    radiant_win = models.BooleanField()
    duration = models.IntegerField()
    start_time = models.IntegerField()
    game_mode = models.IntegerField()
    lobby_type = models.IntegerField()

    def __str__(self):
        return str(self.match_id)


class PlayerMatchStats(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="players")
    steam_id = models.BigIntegerField()
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
