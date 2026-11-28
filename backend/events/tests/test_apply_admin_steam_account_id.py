import time

from django.test import SimpleTestCase

from app.models import CustomUser
from events.eligibility.steam import apply_admin_steam_account_id


class ApplyAdminSteamAccountIdClearTests(SimpleTestCase):
    def test_clearing_returns_without_scanning_the_id_range(self) -> None:
        user = CustomUser(username="clear-target", steam_account_id=765353)
        actor = CustomUser(username="clear-actor")

        started = time.monotonic()
        grant = apply_admin_steam_account_id(user, None, actor=actor)
        elapsed = time.monotonic() - started

        self.assertIsNone(grant)
        self.assertIsNone(user.steam_account_id)
        self.assertLess(elapsed, 1.0)
