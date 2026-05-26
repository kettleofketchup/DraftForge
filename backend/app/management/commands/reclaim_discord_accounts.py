"""Reclaim Discord accounts split by the phantom-signup bug.

A Discord button signup created accounts carrying `discordId` for people who
never logged in. A later failed OAuth login created a *second* row holding the
social-auth link. This command finds those split pairs and merges the duplicate
login row back into the account that owns the `discordId` (and the signups).

Dry-run by default. Pass --apply to actually merge.

    python manage.py reclaim_discord_accounts          # preview
    python manage.py reclaim_discord_accounts --apply   # merge
"""

from django.core.management.base import BaseCommand

from app.discord_accounts import find_split_discord_accounts, merge_discord_accounts


class Command(BaseCommand):
    help = "Merge duplicate Discord login accounts back into the phantom-signup account that owns the discordId."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually merge the accounts (default is a dry-run preview).",
        )

    def handle(self, *args, **options):
        pairs = find_split_discord_accounts()
        if not pairs:
            self.stdout.write(self.style.SUCCESS("No split Discord accounts found."))
            return

        apply = options["apply"]
        for keep, drop in pairs:
            self.stdout.write(
                f"discordId={keep.discordId}: keep #{keep.pk} ({keep.username}) "
                f"<- merge social-login #{drop.pk} ({drop.username})"
            )
            if apply:
                merge_discord_accounts(keep=keep, drop=drop)
                self.stdout.write(
                    self.style.SUCCESS(f"  merged and deleted account #{drop.pk}")
                )

        if apply:
            self.stdout.write(
                self.style.SUCCESS(f"Merged {len(pairs)} account pair(s).")
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"Dry-run: found {len(pairs)} split pair(s). "
                    "Re-run with --apply to merge."
                )
            )
