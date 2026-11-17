from app.models import CustomUser, GameType
from events.discord.providers.deadlock import DeadlockHandler
from events.discord.providers.dota import DotaHandler
from events.models import EventSignup
from events.tests.base import EventTestCase
from org.models import OrgUser
from org.models_profiles import PlayerDeadlockProfile, PlayerDotaProfile


class FriendIdModalTests(EventTestCase):
    def _org_user(self, user: CustomUser) -> OrgUser:
        return OrgUser.objects.get(user=user, organization=self.org)

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
                    {"unverified_friend_id": fid, "deadlock_rank": "Ritualist"},
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
            {"unverified_friend_id": " 515151 ", "deadlock_rank": "Ritualist"},
        )
        self.assertEqual(result["action"], "signed_up")
        self.assertEqual(
            PlayerDeadlockProfile.objects.get(org_user=ou).unverified_friend_id,
            "515151",
        )

    def test_dota_modal_rejects_bad_friend_id(self) -> None:
        ev = self.make_event()
        for fid in ("abc", "9" * 21, self._taken_friend_id()):
            with self.subTest(fid=fid):
                u = self.make_user()
                ou = self._org_user(u)
                result = DotaHandler().apply_modal_submit(
                    ev, ou, u, {"unverified_friend_id": fid, "rank_status": "active"}
                )
                self.assertEqual(result["action"], "error")
                self.assertTrue(result["message"])
                self.assertFalse(PlayerDotaProfile.objects.filter(org_user=ou).exists())
                self.assertFalse(EventSignup.objects.filter(event=ev, user=u).exists())
