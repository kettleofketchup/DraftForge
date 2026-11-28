from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from app.models import CustomUser
from org.api_connections.promotion_config import (
    PromotionStreamError,
    adopt_legacy_promotion,
)


class Command(BaseCommand):
    help = (
        "Move a deployment-bound org's promotion contact sync onto one of its "
        "API connections, using a per-org adaptor credential. Push stays off."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--org", type=int, required=True)
        parser.add_argument("--operator", required=True, help="Superuser username.")
        parser.add_argument("--base-url", required=True)
        parser.add_argument(
            "--credential-file",
            required=True,
            help="File holding the adaptor credential issued for this org alone.",
        )
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        actor = CustomUser.objects.filter(username=options["operator"]).first()
        if actor is None:
            raise CommandError("operator_required")
        try:
            with open(options["credential_file"], encoding="utf-8") as fh:
                credential = fh.read().strip()
        except (OSError, UnicodeDecodeError):
            raise CommandError("credential_file_unreadable") from None
        try:
            connection = adopt_legacy_promotion(
                org_id=options["org"],
                actor=actor,
                credential=credential,
                base_url=options["base_url"],
                dry_run=options["dry_run"],
            )
        except PromotionStreamError as exc:
            raise CommandError(exc.code) from None
        verb = "would adopt" if options["dry_run"] else "adopted"
        self.stdout.write(
            f"org {options['org']} {verb} promotion stream on connection "
            f"{connection.pk}"
        )
