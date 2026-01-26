import logging

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()


class Command(BaseCommand):
    help = "Refresh Discord avatars for all users"

    def add_arguments(self, parser):
        parser.add_argument(
            "--check-only",
            action="store_true",
            help="Only check for invalid avatars without updating",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force refresh all avatars regardless of validity",
        )
        parser.add_argument(
            "--user-id",
            type=int,
            help="Refresh avatar for specific user ID only",
        )

    def handle(self, *args, **options):
        check_only = options["check_only"]
        force_refresh = options["force"]
        user_id = options["user_id"]

        if user_id:
            users = User.objects.filter(id=user_id, discordId__isnull=False)
            if not users.exists():
                self.stdout.write(
                    self.style.ERROR(
                        f"User with ID {user_id} not found or has no Discord ID"
                    )
                )
                return
        else:
            users = User.objects.filter(discordId__isnull=False)

        total_users = users.count()
        self.stdout.write(f"Processing {total_users} users with Discord IDs...")

        updated_count = 0
        invalid_count = 0

        for user in users:
            try:
                if check_only:
                    # Just check if current avatar URL is valid
                    current_url = f"https://cdn.discordapp.com/avatars/{user.discordId}/{user.avatar}"
                    if not user._is_avatar_url_valid(current_url):
                        invalid_count += 1
                        self.stdout.write(
                            self.style.WARNING(
                                f"Invalid avatar for {user.username}: {current_url}"
                            )
                        )
                else:
                    # check_and_update_avatar() checks and updates the avatar
                    updated = user.check_and_update_avatar()

                    if updated:
                        updated_count += 1
                        self.stdout.write(
                            self.style.SUCCESS(f"Updated avatar for {user.username}")
                        )

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"Error processing {user.username}: {str(e)}")
                )

        if check_only:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Check complete. Found {invalid_count} invalid avatars out of {total_users} users."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Refresh complete. Updated {updated_count} avatars out of {total_users} users."
                )
            )
