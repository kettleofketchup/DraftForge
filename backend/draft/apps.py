from django.apps import AppConfig


class DraftConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "draft"
    label = "draft"

    def ready(self) -> None:
        import draft.signals  # noqa: F401
