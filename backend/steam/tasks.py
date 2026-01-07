import logging

from celery import shared_task

from steam.constants import LEAGUE_ID
from steam.functions.league_sync import sync_league_matches
from steam.functions.stats_update import update_all_league_stats_for_league

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def sync_league_matches_task(self, league_id: int = None):
    """
    Fetch new matches from Steam API for a league.
    Scheduled to run every minute.
    """
    if league_id is None:
        league_id = LEAGUE_ID

    logger.info(f"Starting league sync for league {league_id}")

    try:
        result = sync_league_matches(league_id, full_sync=False)
        logger.info(
            f"League sync complete: {result['synced_count']} synced, "
            f"{result['failed_count']} failed"
        )

        # If new matches were synced, update stats
        if result["synced_count"] > 0:
            update_league_stats_task.delay(league_id)

        return result
    except Exception as exc:
        logger.error(f"League sync failed: {exc}")
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True)
def update_league_stats_task(self, league_id: int = None):
    """
    Update LeaguePlayerStats for all users in a league.
    Called after new matches are synced.
    """
    if league_id is None:
        league_id = LEAGUE_ID

    logger.info(f"Updating league stats for league {league_id}")

    try:
        updated_count = update_all_league_stats_for_league(league_id)
        logger.info(f"Updated stats for {updated_count} users")
        return {"updated_count": updated_count}
    except Exception as exc:
        logger.error(f"Stats update failed: {exc}")
        raise


@shared_task
def recalculate_user_league_mmr_task(user_id: int):
    """
    Recalculate a single user's league_mmr.
    Useful for manual recalculation.
    """
    from app.models import CustomUser
    from steam.functions.mmr_calculation import update_user_league_mmr

    try:
        user = CustomUser.objects.get(pk=user_id)
        update_user_league_mmr(user)
        logger.info(f"Recalculated league MMR for {user.username}: {user.league_mmr}")
        return {"user_id": user_id, "league_mmr": user.league_mmr}
    except CustomUser.DoesNotExist:
        logger.error(f"User {user_id} not found")
        return None
