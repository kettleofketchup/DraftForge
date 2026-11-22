from django.apps import AppConfig


class OrgConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "org"

    def ready(self) -> None:
        import org.signals  # noqa: F401
