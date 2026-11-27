"""Test-only settings: the normal settings on a throwaway local PostgreSQL.

Used only by ``just test::backend::pg-race``, which starts a disposable
PostgreSQL container and passes its DSN in ``DF_PGTEST_DSN``. The DSN must
point at localhost, so these settings cannot reach a shared or production
database. Production and the default test suite stay on SQLite.
"""

import os
from urllib.parse import unquote, urlsplit

from backend.settings import *  # noqa: F403
from backend.settings import DATABASES

_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _pg_database(dsn: str) -> dict[str, object]:
    parts = urlsplit(dsn)
    if parts.scheme not in ("postgres", "postgresql"):
        raise RuntimeError("DF_PGTEST_DSN must be a postgresql:// URL")
    if parts.hostname not in _LOCAL_HOSTS:
        raise RuntimeError("DF_PGTEST_DSN must point at a local throwaway server")
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": parts.path.lstrip("/"),
        "USER": unquote(parts.username or ""),
        "PASSWORD": unquote(parts.password or ""),
        "HOST": parts.hostname,
        "PORT": str(parts.port or 5432),
    }


class _NoMigrations(dict):
    """Build the test schema from the current models.

    The migration history was only ever applied to SQLite and does not
    replay on PostgreSQL (an app move recreates an existing constraint).
    These runs test runtime locking, not migrations, so the schema comes
    straight from the models.
    """

    def __contains__(self, item: object) -> bool:
        return True

    def __getitem__(self, item: str) -> None:
        return None


DATABASES["default"] = _pg_database(os.environ["DF_PGTEST_DSN"])
MIGRATION_MODULES = _NoMigrations()
