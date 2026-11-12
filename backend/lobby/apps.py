from django.apps import AppConfig


class LobbyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "lobby"
    verbose_name = "Dota 2 lobbies"

    def ready(self) -> None:
        from lobby import signals  # noqa: F401 - connects the receivers
