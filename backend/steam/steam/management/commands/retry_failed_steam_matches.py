import logging

from django.core.management.base import BaseCommand

from steam.constants import LEAGUE_ID
from steam.functions.league_sync import retry_failed_matches

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Retry fetching failed Steam matches"

    def add_arguments(self, parser):
        parser.add_argument(
            "--league-id",
            type=int,
            default=LEAGUE_ID,
            help=f"League ID to retry failed matches for (default: {LEAGUE_ID})",
        )

    def handle(self, *args, **options):
        league_id = options.get("league_id", LEAGUE_ID)

        self.stdout.write(f"Retrying failed matches for league {league_id}...")

        try:
            result = retry_failed_matches(league_id)

            self.stdout.write(
                self.style.SUCCESS(
                    f"Retried {result['synced_count']} matches, "
                    f"{result['failed_count']} still failing"
                )
            )

            if result["failed_count"] > 0:
                self.stdout.write(
                    self.style.WARNING(
                        f"{result['failed_count']} matches still failing. "
                        "Check Steam API availability and try again later."
                    )
                )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error retrying matches: {str(e)}"))
            logger.error(
                f"Error in retry_failed_steam_matches command: {str(e)}", exc_info=True
            )
            raise
