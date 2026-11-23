from django.core.management.base import BaseCommand

from tournament.services.team_leadership import teams_with_leadership_problems


class Command(BaseCommand):
    help = (
        "List teams whose captain or deputy is not a member, or whose deputy is "
        "the captain. Read-only."
    )

    def handle(self, *args: object, **options: object) -> None:
        rows = teams_with_leadership_problems()
        for team, problem in rows:
            self.stdout.write(
                f"team={team.pk} tournament={team.tournament_id} problem={problem}"
            )
        self.stdout.write(f"{len(rows)} leadership problem(s) found.")
