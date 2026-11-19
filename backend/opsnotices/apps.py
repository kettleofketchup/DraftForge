from django.apps import AppConfig
from django.utils.module_loading import autodiscover_modules


class OpsNoticesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "opsnotices"
    verbose_name = "Operations notices"

    def ready(self) -> None:
        autodiscover_modules("ops_notices")
