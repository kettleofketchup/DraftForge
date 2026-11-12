import os
from pathlib import Path
from typing import Any

from django.test.runner import DiscoverRunner
from django.test.utils import override_settings

from config.dota_lobby import DotaLobbyConfig

BACKEND_DIR: str = str(Path(__file__).resolve().parent.parent)

DOTA_LOBBY_ENV_PREFIX = "DOTA_LOBBY_"


def default_dota_lobby_settings() -> dict[str, Any]:
    """The DOTA_LOBBY_* settings of an environment that sets none of them."""
    config = DotaLobbyConfig.from_env({})
    return {
        "DOTA_LOBBY_ENABLED": config.enabled,
        "DOTA_LOBBY_URL": config.url,
        "DOTA_LOBBY_API_KEY": config.api_key,
        "DOTA_LOBBY_WEBHOOK_SECRETS": config.webhook_secrets,
        "DOTA_LOBBY_TIMEOUT_SECONDS": config.timeout_seconds,
        "DOTA_LOBBY_REF_PREFIX": config.ref_prefix,
        "DOTA_LOBBY_WEBHOOK_TOLERANCE_SECONDS": config.webhook_tolerance_seconds,
        "DOTA_LOBBY_REGION": config.region,
    }


class BackendDiscoverRunner(DiscoverRunner):
    """Anchor discovery at backend/ so modules import as `app.tests...`.

    backend/ and the repo root both hold an __init__.py, so unittest would
    otherwise walk the top-level directory up past backend/.

    The test stack turns dota_lobby on for Playwright (docker/.env.test), and
    the unit tests run in that stack. They start from the defaults instead,
    lobbies off and no service URL, and turn them on per test
    (lobby.tests.helpers.lobby_settings). The DOTA_LOBBY_* variables are also
    taken out of the environment, which DotaLobbyClient reads, before any
    parallel worker starts.
    """

    def __init__(self, *args: Any, top_level: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, top_level=top_level or BACKEND_DIR, **kwargs)
        self._dota_lobby_env: dict[str, str] = {}
        self._dota_lobby_settings: override_settings | None = None

    def setup_test_environment(self, **kwargs: Any) -> None:
        super().setup_test_environment(**kwargs)
        self._dota_lobby_env = {
            key: os.environ.pop(key)
            for key in list(os.environ)
            if key.startswith(DOTA_LOBBY_ENV_PREFIX)
        }
        self._dota_lobby_settings = override_settings(**default_dota_lobby_settings())
        self._dota_lobby_settings.enable()

    def teardown_test_environment(self, **kwargs: Any) -> None:
        if self._dota_lobby_settings is not None:
            self._dota_lobby_settings.disable()
            self._dota_lobby_settings = None
        os.environ.update(self._dota_lobby_env)
        self._dota_lobby_env = {}
        super().teardown_test_environment(**kwargs)
