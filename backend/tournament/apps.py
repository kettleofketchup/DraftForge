from django.apps import AppConfig


class TournamentConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tournament"

    def ready(self) -> None:
        import tournament.signals  # noqa: F401
