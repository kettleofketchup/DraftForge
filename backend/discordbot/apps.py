from django.apps import AppConfig


class DiscordbotConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "discordbot"

    def ready(self) -> None:
        from discordbot.live_signals import connect_live_signals

        connect_live_signals()
