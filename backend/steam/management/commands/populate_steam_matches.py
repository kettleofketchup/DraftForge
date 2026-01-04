import logging

from django.core.management.base import BaseCommand

from steam.constants import LEAGUE_ID
from steam.functions.league_sync import relink_all_users, sync_league_matches

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Populate the database with Steam match data from the real Steam API"

    def add_arguments(self, parser):
        parser.add_argument(
            "--league-id",
            type=int,
            default=LEAGUE_ID,
            help=f"League ID to fetch matches from (default: {LEAGUE_ID})",
        )
        parser.add_argument(
            "--full-sync",
            action="store_true",
            help="Perform a full sync (fetch all matches, not just new ones)",
        )
        parser.add_argument(
            "--relink-users",
            action="store_true",
            help="Re-link all users to their match stats after syncing",
        )

    def handle(self, *args, **options):
        league_id = options.get("league_id", LEAGUE_ID)
        full_sync = options.get("full_sync", False)
        relink = options.get("relink_users", False)

        self.stdout.write(f"Fetching matches from Steam API for league {league_id}...")
        self.stdout.write(f"Mode: {'Full sync' if full_sync else 'Incremental sync'}")

        try:
            result = sync_league_matches(league_id, full_sync=full_sync)

            self.stdout.write(
                self.style.SUCCESS(
                    f"Synced {result['synced_count']} matches, "
                    f"{result['failed_count']} failed"
                )
            )

            if result["new_last_match_id"]:
                self.stdout.write(f"Last match ID: {result['new_last_match_id']}")

            if result["failed_count"] > 0:
                self.stdout.write(
                    self.style.WARNING(
                        f"Some matches failed to sync. Run 'python manage.py retry_failed_steam_matches' to retry."
                    )
                )

            if relink:
                self.stdout.write("Re-linking users to match stats...")
                linked_count = relink_all_users()
                self.stdout.write(
                    self.style.SUCCESS(f"Linked {linked_count} player stats to users")
                )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error syncing matches: {str(e)}"))
            logger.error(
                f"Error in populate_steam_matches command: {str(e)}", exc_info=True
            )
            raise
