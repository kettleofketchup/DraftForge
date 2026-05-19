from django.apps import AppConfig


class AppConfig(AppConfig):
    name = "app"

    def ready(self):
        """Register signal handlers. Do NOT invalidate the cache here.

        Previously this called `cacheops.invalidate_all()` on every boot
        to defend against stale cached payloads after code changes. The
        cost was a fully cold cache on every Daphne reload, healthcheck
        restart, OOM kill, and pod replacement — which then made every
        request hit SQLite.

        Cache freshness now flows from two cheaper mechanisms:

        * `CACHEOPS_PREFIX` in settings — prefixes every cache key with
          the deploy version. New deploys orphan old keys automatically
          while restarts within the same deploy stay warm.
        * `post_save`/`post_delete` signals registered by cacheops for
          every model with `ops="all"` — writes invalidate the rows
          they touch.

        Schema-change migrations that need to wipe a specific model's
        cache should call `invalidate_model(Model)` from inside the
        migration (see e.g. `discordbot/migrations/0009_*`).
        """
        import app.signals  # noqa: F401
