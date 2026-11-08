LEAGUE_ID = 17929

# Steam omits these until it finishes parsing a match; storing defaults would
# guess (player_slot 0 = Radiant), so ingest paths reject and retry instead.
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
