from django.apps import AppConfig


class AppConfig(AppConfig):
    name = "app"

    def ready(self):
        """Register signal handlers; cache freshness handled elsewhere.

        Production relies on two cheaper mechanisms than the previous
        `invalidate_all()` on every boot:

        * `CACHEOPS_PREFIX` in settings — prefixes every cache key with
          the deploy version. New deploys orphan old keys automatically
          while restarts within the same deploy stay warm.
        * `post_save`/`post_delete` signals registered by cacheops for
          every model with `ops="all"` — writes invalidate the rows
          they touch.

        Test/dev environments DO want a hard reset on boot — rapid
        schema iteration, populate scripts that bypass signals, and
        test-suite state from previous runs can leave the cache out
        of sync with the DB. So when `NODE_ENV` is `test` or `dev`
        (or `TEST=true` env), `invalidate_all()` still fires. In
        prod the cache survives restarts.

        Schema-change migrations that need to wipe a specific model's
        cache should call `invalidate_model(Model)` from inside the
        migration (see e.g. `discordbot/migrations/0009_*`).
        """
        import os

        import app.signals  # noqa: F401

        if os.environ.get("DISABLE_CACHE", "false").lower() == "true":
            return

        node_env = os.environ.get("NODE_ENV", "").lower()
        is_test_env = (
            node_env in ("test", "dev")
            or os.environ.get("TEST", "").lower() == "true"
        )
        if not is_test_env:
            return

        try:
            from cacheops import invalidate_all

            invalidate_all()
        except Exception:
            # Redis unreachable on boot — let the app continue, cacheops
            # has CACHEOPS_DEGRADE_ON_FAILURE=True for read-side resilience.
            pass
