from unittest.mock import patch

from django.core.cache import cache
from django.test import override_settings

from app.models import CustomUser, GameType
from events.discord import handle_signup_modal_submit
from events.discord._shared import _direct_signup
from events.discord.providers.deadlock import DeadlockHandler
from events.discord.providers.dota import DotaHandler
from events.models import EventSignup, SignupStatus
from events.tests.base import EventTestCase
from org.membership import resolve_or_create_org_user
from org.models import OrgUser
from org.models_profiles import PlayerDeadlockProfile, PlayerDotaProfile
from steam.services.account_lookup import SteamLookupRateLimited


class FriendIdModalTests(EventTestCase):
    def _org_user(self, user: CustomUser) -> OrgUser:
        return resolve_or_create_org_user(user, self.org)

    def _taken_friend_id(self) -> str:
        other = self.make_user()
        other.steam_account_id = 818181
        other.save()
        return "818181"

    def test_deadlock_modal_rejects_bad_friend_id(self) -> None:
        ev = self.make_event(game_type=GameType.DEADLOCK)
        for fid in ("abc", "9" * 21, self._taken_friend_id()):
            with self.subTest(fid=fid):
                u = self.make_user()
                ou = self._org_user(u)
                result = DeadlockHandler().apply_modal_submit(
                    ev,
                    ou,
                    u,
                    {"friend_id": fid, "deadlock_rank": "Ritualist"},
                )
                self.assertEqual(result["action"], "error")
                self.assertTrue(result["message"])
                self.assertFalse(
                    PlayerDeadlockProfile.objects.filter(org_user=ou).exists()
                )
                self.assertFalse(EventSignup.objects.filter(event=ev, user=u).exists())

    def test_deadlock_modal_saves_stripped_friend_id(self) -> None:
        ev = self.make_event(game_type=GameType.DEADLOCK)
        u = self.make_user()
        ou = self._org_user(u)
        result = DeadlockHandler().apply_modal_submit(
            ev,
            ou,
            u,
            {"friend_id": " 515151 ", "deadlock_rank": "Ritualist"},
        )
        self.assertEqual(result["action"], "signed_up")
        u.refresh_from_db()
        self.assertEqual(u.steam_account_id, 515151)
        self.assertEqual(u.steamid, 515151 + CustomUser.STEAM_ID_64_BASE)

    def test_modals_fill_the_user_with_ids_above_signed_32_bit(self) -> None:
        cases = (
            (DeadlockHandler(), GameType.DEADLOCK, {"deadlock_rank": "Ritualist"}),
            (DotaHandler(), GameType.DOTA2, {"rank_status": "active"}),
        )
        for offset, (handler, game_type, extra) in enumerate(cases):
            with self.subTest(game_type=game_type):
                ev = self.make_event(game_type=game_type)
                u = self.make_user()
                fid = 2**32 - 1 - offset
                result = handler.apply_modal_submit(
                    ev, self._org_user(u), u, {"friend_id": str(fid), **extra}
                )
                self.assertNotEqual(result["action"], "error", result)
                u.refresh_from_db()
                self.assertEqual(u.steam_account_id, fid)

    def test_modals_refuse_a_different_friend_id(self) -> None:
        cases = (
            (DeadlockHandler(), GameType.DEADLOCK, {"deadlock_rank": "Ritualist"}),
            (DotaHandler(), GameType.DOTA2, {"rank_status": "active"}),
        )
        for offset, (handler, game_type, extra) in enumerate(cases):
            with self.subTest(game_type=game_type):
                ev = self.make_event(game_type=game_type)
                u = self.make_user()
                u.steam_account_id = 909090 + offset
                u.save()
                result = handler.apply_modal_submit(
                    ev, self._org_user(u), u, {"friend_id": "121212", **extra}
                )
                self.assertEqual(result["action"], "error")
                self.assertIn("already set", result["message"])
                u.refresh_from_db()
                self.assertEqual(u.steam_account_id, 909090 + offset)
                self.assertFalse(EventSignup.objects.filter(event=ev, user=u).exists())

    def test_modals_accept_the_same_friend_id(self) -> None:
        ev = self.make_event(game_type=GameType.DEADLOCK)
        u = self.make_user()
        u.steam_account_id = 343434
        u.save()
        result = DeadlockHandler().apply_modal_submit(
            ev, self._org_user(u), u, {"friend_id": "343434", "deadlock_rank": "R"}
        )
        self.assertEqual(result["action"], "signed_up")
        u.refresh_from_db()
        self.assertEqual(u.steam_account_id, 343434)

    def test_prefill_reads_the_user(self) -> None:
        u = self.make_user()
        ou = self._org_user(u)
        self.assertEqual(DotaHandler().prefill(ou), {"friend_id": ""})
        u.steam_account_id = 3000000000
        u.save()
        for handler in (DotaHandler(), DeadlockHandler()):
            with self.subTest(handler=type(handler).__name__):
                self.assertEqual(handler.prefill(ou), {"friend_id": "3000000000"})

    def test_deadlock_friend_id_refreshes_codes_on_other_signups(self) -> None:
        dota_ev = self.make_event(auto_approve=False, require_steam_id=True)
        u = self.make_user()
        held = EventSignup.objects.create(
            event=dota_ev,
            user=u,
            status=SignupStatus.RSVP,
            unmet_requirements=["steam_id_missing"],
        )
        result = DeadlockHandler().apply_modal_submit(
            self.make_event(game_type=GameType.DEADLOCK),
            self._org_user(u),
            u,
            {"friend_id": "535353", "deadlock_rank": "Ritualist"},
        )
        self.assertEqual(result["action"], "signed_up")
        held.refresh_from_db()
        self.assertEqual(held.unmet_requirements, [])

    def test_dota_modal_rejects_bad_friend_id(self) -> None:
        ev = self.make_event()
        for fid in ("abc", "9" * 21, self._taken_friend_id()):
            with self.subTest(fid=fid):
                u = self.make_user()
                ou = self._org_user(u)
                result = DotaHandler().apply_modal_submit(
                    ev, ou, u, {"friend_id": fid, "rank_status": "active"}
                )
                self.assertEqual(result["action"], "error")
                self.assertTrue(result["message"])
                self.assertFalse(PlayerDotaProfile.objects.filter(org_user=ou).exists())
                self.assertFalse(EventSignup.objects.filter(event=ev, user=u).exists())


class FriendIdModalLoggingTests(EventTestCase):
    def _assert_logged(self, module: str, handler: object, ev: object) -> None:
        u = self.make_user()
        ou = resolve_or_create_org_user(u, self.org)
        with patch(f"events.discord.providers.{module}.log") as log:
            result = handler.apply_modal_submit(
                ev,
                ou,
                u,
                {
                    "friend_id": "abc",
                    "deadlock_rank": "Ritualist",
                    "rank_status": "active",
                },
            )
        self.assertEqual(result["action"], "error")
        log.info.assert_any_call(
            "signup_input_rejected",
            system="discord",
            subsystem="interaction",
            reason="invalid_friend_id",
        )
        for call in log.info.call_args_list:
            self.assertNotIn("abc", call.kwargs.values())

    def test_deadlock_logs_rejection(self) -> None:
        self._assert_logged(
            "deadlock", DeadlockHandler(), self.make_event(game_type=GameType.DEADLOCK)
        )

    def test_dota_logs_rejection(self) -> None:
        self._assert_logged("dota", DotaHandler(), self.make_event())


class DotaModalDirectSignupTests(EventTestCase):
    def test_fresh_friend_id_then_direct_signup_is_approved(self) -> None:
        ev = self.make_event(require_steam_id=True)
        u = self.make_user()
        ou = resolve_or_create_org_user(u, self.org)
        result = DotaHandler().apply_modal_submit(ev, ou, u, {"friend_id": "626262"})
        self.assertEqual(result["action"], "needs_rank_status")
        reply = _direct_signup(ev, u)
        self.assertEqual(reply["status"], SignupStatus.APPROVED)
        u.refresh_from_db()
        self.assertEqual(u.steam_account_id, 626262)


@override_settings(
    STEAM_ACCOUNT_LOOKUP_ENABLED=True,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class ModalSubmitSteamLookupTests(EventTestCase):
    ENSURE = "events.eligibility.steam.ensure_steam_account_exists"
    CASES = (
        (GameType.DOTA2, {"rank_status": "active"}),
        (GameType.DEADLOCK, {"deadlock_rank": "Ritualist"}),
    )

    def setUp(self) -> None:
        cache.clear()

    def _submit(self, game_type: int, extra: dict, fid: str) -> tuple[dict, CustomUser]:
        ev = self.make_event(game_type=game_type, require_steam_id=True)
        user = self.make_user()
        user.discordId = f"55500{user.pk}"
        user.save()
        result = handle_signup_modal_submit(
            event_id=ev.pk,
            discord_user_id=user.discordId,
            game_type=game_type,
            values={"friend_id": fid, **extra},
        )
        self.assertFalse(EventSignup.objects.filter(event=ev, user=user).exists())
        user.refresh_from_db()
        return result, user

    def test_modal_submit_not_found_message(self) -> None:
        for game_type, extra in self.CASES:
            with self.subTest(game_type=game_type):
                with patch(self.ENSURE, return_value=False):
                    result, user = self._submit(game_type, extra, "646464")
                self.assertEqual(result["action"], "error")
                self.assertIn(
                    "No Steam account has Friend ID 646464", result["message"]
                )
                self.assertIsNone(user.steam_account_id)

    def test_modal_submit_rate_limited_message(self) -> None:
        for game_type, extra in self.CASES:
            with self.subTest(game_type=game_type):
                with patch(self.ENSURE, side_effect=SteamLookupRateLimited()):
                    result, user = self._submit(game_type, extra, "656565")
                self.assertEqual(result["action"], "error")
                self.assertEqual(
                    result["message"],
                    "Too many Friend ID checks. Try again in an hour.",
                )
                self.assertIsNone(user.steam_account_id)
