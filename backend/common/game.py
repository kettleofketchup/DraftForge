from django.db import models


class GameType(models.IntegerChoices):
    """Integer codes for the supported games.

    Re-exported from `app.models`. KEEP IN SYNC with frontend:
    `frontend/app/components/game/constants.ts` (`GAME_TYPE`). When adding a new game, update BOTH files. The numeric IDs
    MUST match — they are persisted in `Event.game_type`,
    `OrgEventDefaults.game_type`, etc.
    """

    DOTA2 = 1, "Dota 2"
    DEADLOCK = 2, "Deadlock"
