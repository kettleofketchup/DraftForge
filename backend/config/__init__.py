import os

# Don't import the full Celery app when using lightweight settings —
# celery_light.py has its own Celery app and handles init itself.
if os.environ.get("DJANGO_SETTINGS_MODULE") != "config.settings_celery":
    from .celery import app as celery_app

    __all__ = ("celery_app",)
