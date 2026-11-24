from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.db import connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone as tz
from rest_framework.test import APIClient

from app.models import CustomUser, GameType, PositionsModel
from events.constants import EventState
from events.discord import handle_signup_modal_submit
from events.models import Event
from org.models import Organization, OrgUser

ENSURE = "events.eligibility.steam.ensure_steam_account_exists"


@override_settings(
    STEAM_ACCOUNT_LOOKUP_ENABLED=True,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class SignupLookupOutsideAtomicTest(TransactionTestCase):
    def setUp(self) -> None:
        cache.clear()
        self.owner = CustomUser.objects.create(username="sla-owner")
        self.org = Organization.objects.create(name="SLA Org", owner=self.owner)
        self.user = CustomUser.objects.create(
            username="sla-user",
            discordId="100000000000000777",
            positions=PositionsModel.objects.create(),
        )
        OrgUser.objects.create(user=self.user, organization=self.org)
        self.seen: list[bool] = []

    def _event(self, game_type: int) -> Event:
        return Event.objects.create(
            organization=self.org,
            name=f"SLA Event {game_type}",
            scheduled_at=tz.now() + timedelta(days=7),
            state=EventState.SIGNUPS_OPEN,
            created_by=self.owner,
            auto_approve=True,
            game_type=game_type,
            require_steam_id=True,
            require_mmr_verified=False,
            require_profile_complete=False,
        )

    def _ensure(self, *_args: object, **_kwargs: object) -> bool:
        self.seen.append(connection.in_atomic_block)
        return True

    def test_web_signup_lookup_outside_atomic(self) -> None:
        ev = self._event(GameType.DOTA2)
        client = APIClient()
        client.force_authenticate(self.user)
        with patch(ENSURE, side_effect=self._ensure):
            resp = client.post(
                f"/api/events/{ev.pk}/signup/",
                {"intent": "rsvp", "profile": {"steam_account_id": "616161"}},
                format="json",
            )
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(self.seen, [False])
        self.assertEqual(
            CustomUser.objects.get(pk=self.user.pk).steam_account_id, 616161
        )

    def test_modal_submit_lookup_outside_atomic(self) -> None:
        cases = (
            (GameType.DOTA2, {"rank_status": "active"}, 626262),
            (GameType.DEADLOCK, {"deadlock_rank": "Ritualist"}, 636363),
        )
        for game_type, extra, fid in cases:
            with self.subTest(game_type=game_type):
                CustomUser.objects.filter(pk=self.user.pk).update(
                    steam_account_id=None, steamid=None
                )
                self.seen.clear()
                ev = self._event(game_type)
                with patch(ENSURE, side_effect=self._ensure):
                    result = handle_signup_modal_submit(
                        event_id=ev.pk,
                        discord_user_id=self.user.discordId,
                        game_type=game_type,
                        values={"friend_id": str(fid), **extra},
                    )
                self.assertNotEqual(result["action"], "error", result)
                self.assertEqual(self.seen, [False])
                self.assertEqual(
                    CustomUser.objects.get(pk=self.user.pk).steam_account_id, fid
                )
