"""Single source of truth for INSTALLED_APPS shared across processes.

Two Python processes load Django settings:

- The web/backend process (Daphne, `backend.settings`) — has DB access,
  runs all middleware, registers admin/REST etc.
- The celery worker process (`config.settings_celery`) — no DB
  (`DATABASES = {}`), no web stack; goes through the internal HTTP API
  for any data work.

Both still need the same set of *model-bearing* apps registered:
celery's task autodiscovery imports task modules, which import handler
modules, which import model classes — and Django's Model metaclass
refuses to define a class whose `app_label` isn't in `INSTALLED_APPS`.

Drift between the two lists has bitten us (e.g. `org` being added for
PlayerDotaProfile imports without a matching celery update). Keep that
shared subset here.
"""

MODEL_APPS: list[str] = [
    "app",
    "events",
    "discordbot",
    "steam",
    "org",
]
