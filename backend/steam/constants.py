LEAGUE_ID = 17929

# Steam omits these until it finishes parsing a match; storing defaults would
# guess (player_slot 0 = Radiant), so ingest rejects and retries instead.
# views_internal.store_match still keeps an inline copy of the player list.
REQUIRED_MATCH_FIELDS: tuple[str, ...] = (
    "radiant_win",
    "duration",
    "start_time",
    "game_mode",
    "lobby_type",
)
REQUIRED_PLAYER_FIELDS: tuple[str, ...] = (
    "player_slot",
    "hero_id",
    "kills",
    "deaths",
    "assists",
    "gold_per_min",
    "xp_per_min",
    "last_hits",
    "denies",
    "hero_damage",
    "tower_damage",
    "hero_healing",
)
