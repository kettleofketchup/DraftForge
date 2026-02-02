"""
Populate test authentication users for Playwright/Cypress testing.

Reference: docs/testing/auth/fixtures.md
If you update these users, also update the documentation!
"""

import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Populate test authentication users for E2E testing"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force populate even if users already exist",
        )

    def handle(self, *args, **options):
        force = options.get("force", False)

        from tests.populate import populate_test_auth_users

        try:
            self.stdout.write("Starting test auth user population...")
            populate_test_auth_users(force=force)
            self.stdout.write(
                self.style.SUCCESS("Successfully populated test auth users!")
            )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Error populating test auth users: {str(e)}")
            )
            logger.error(
                f"Error in populate_test_auth_users command: {str(e)}", exc_info=True
            )
            raise
