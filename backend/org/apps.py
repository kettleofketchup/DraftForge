from django.apps import AppConfig


class OrgConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "org"

    def ready(self) -> None:
        import org.mmr_bridge  # noqa: F401
        import org.signals  # noqa: F401
