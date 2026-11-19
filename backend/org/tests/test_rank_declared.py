from django.test import TestCase
from django.urls import reverse
from rest_framework.response import Response
from rest_framework.test import APIClient

from app.models import CustomUser, Organization
from org.models import OrgUser
from org.models_profiles import PlayerDotaProfile
from org.tests.rank_evidence_cases import RANK_EVIDENCE_CASES


class DeclareRankTest(TestCase):
    def test_declare_rank_sets_status_and_timestamp(self) -> None:
        profile = PlayerDotaProfile()
        self.assertIsNone(profile.rank_declared_at)
        profile.declare_rank("previous")
        self.assertEqual(profile.rank_status, "previous")
        self.assertIsNotNone(profile.rank_declared_at)

    def test_declare_rank_rejects_unknown_status(self) -> None:
        profile = PlayerDotaProfile()
        with self.assertRaises(ValueError):
            profile.declare_rank("x")
        self.assertIsNone(profile.rank_declared_at)

    def test_has_rank_evidence_matches_backfill_rule(self) -> None:
        for key, (fields, expected) in RANK_EVIDENCE_CASES.items():
            with self.subTest(key):
                self.assertEqual(
                    PlayerDotaProfile(**fields).has_rank_evidence(), expected
                )


class RankDeclaredViewTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner = CustomUser.objects.create_user(username="rd_owner", password="x")
        cls.member = CustomUser.objects.create_user(username="rd_member", password="x")
        cls.org = Organization.objects.create(name="Rank Declared Org", owner=cls.owner)
        cls.org.staff.add(cls.owner)
        cls.org_user = OrgUser.objects.create(user=cls.member, organization=cls.org)

    def _profile(self) -> PlayerDotaProfile:
        return PlayerDotaProfile.objects.get(org_user=self.org_user)

    def test_my_profile_patch_with_rank_status_declares(self) -> None:
        client = APIClient()
        client.force_authenticate(self.member)
        url = reverse("update-my-dota-profile", args=[self.org.pk])
        resp = client.patch(url, {"rank_status": "previous"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(self._profile().rank_declared_at)

    def test_my_profile_patch_without_rank_status_leaves_undeclared(self) -> None:
        client = APIClient()
        client.force_authenticate(self.member)
        url = reverse("update-my-dota-profile", args=[self.org.pk])
        resp = client.patch(url, {"pos_1": True}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(self._profile().rank_declared_at)

    def test_staff_patch_with_rank_status_declares(self) -> None:
        client = APIClient()
        client.force_authenticate(self.owner)
        url = reverse("update-user-dota-profile", args=[self.org.pk, self.member.pk])
        resp = client.patch(url, {"rank_status": "active"}, format="json")
        self.assertEqual(resp.status_code, 200)
        profile = self._profile()
        self.assertEqual(profile.rank_status, "active")
        self.assertIsNotNone(profile.rank_declared_at)

    def _member_patch(self, data: dict[str, object]) -> int:
        client = APIClient()
        client.force_authenticate(self.member)
        url = reverse("update-my-dota-profile", args=[self.org.pk])
        return client.patch(url, data, format="json").status_code

    def test_unknown_rank_status_rejected(self) -> None:
        self.assertEqual(self._member_patch({"rank_status": "x"}), 400)
        profile = PlayerDotaProfile.objects.filter(org_user=self.org_user).first()
        if profile is not None:
            self.assertEqual(profile.rank_status, "never")
            self.assertIsNone(profile.rank_declared_at)

    def test_card_style_patch_with_default_status_stays_undeclared(self) -> None:
        status_code = self._member_patch(
            {
                "rank_status": "never",
                "rank_medal": "",
                "battle_cup_tier": None,
                "unverified_friend_id": "123456",
                "pos_1": True,
            }
        )
        self.assertEqual(status_code, 200)
        self.assertIsNone(self._profile().rank_declared_at)

    def test_battle_cup_tier_patch_declares(self) -> None:
        self.assertEqual(self._member_patch({"battle_cup_tier": 3}), 200)
        self.assertIsNotNone(self._profile().rank_declared_at)

    def test_unchanged_status_keeps_declaration_time(self) -> None:
        self.assertEqual(self._member_patch({"rank_status": "active"}), 200)
        first = self._profile().rank_declared_at
        self.assertEqual(
            self._member_patch({"rank_status": "active", "pos_2": True}), 200
        )
        self.assertEqual(self._profile().rank_declared_at, first)


class DotaProfileFriendIdTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner = CustomUser.objects.create_user(username="fid_owner", password="x")
        cls.member = CustomUser.objects.create_user(username="fid_member", password="x")
        cls.other = CustomUser.objects.create_user(username="fid_other", password="x")
        cls.org = Organization.objects.create(name="Friend ID Org", owner=cls.owner)
        cls.org.staff.add(cls.owner)
        cls.org_user = OrgUser.objects.create(user=cls.member, organization=cls.org)
        other_ou = OrgUser.objects.create(user=cls.other, organization=cls.org)
        PlayerDotaProfile.objects.create(org_user=other_ou, unverified_friend_id="5150")
        PlayerDotaProfile.objects.create(
            org_user=cls.org_user, unverified_friend_id="111"
        )

    def _patch(self, actor: CustomUser, url: str, fid: str) -> Response:
        client = APIClient()
        client.force_authenticate(actor)
        return client.patch(
            url, {"unverified_friend_id": fid, "pos_1": True}, format="json"
        )

    def _my_url(self) -> str:
        return reverse("update-my-dota-profile", args=[self.org.pk])

    def _staff_url(self) -> str:
        return reverse("update-user-dota-profile", args=[self.org.pk, self.member.pk])

    def _profile(self) -> PlayerDotaProfile:
        return PlayerDotaProfile.objects.get(org_user=self.org_user)

    def test_rejected_ids_leave_profile_unchanged(self) -> None:
        cases = [
            (self.member, self._my_url(), "5150"),
            (self.member, self._my_url(), "abc"),
            (self.owner, self._staff_url(), "05150"),
        ]
        for actor, url, fid in cases:
            with self.subTest(actor=actor.username, fid=fid):
                resp = self._patch(actor, url, fid)
                self.assertEqual(resp.status_code, 400)
                self.assertTrue(resp.data["unverified_friend_id"])
                profile = self._profile()
                self.assertEqual(profile.unverified_friend_id, "111")
                self.assertFalse(profile.pos_1)

    def test_valid_id_is_stored_canonical(self) -> None:
        resp = self._patch(self.member, self._my_url(), " 0222 ")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._profile().unverified_friend_id, "222")

    def test_empty_id_clears(self) -> None:
        resp = self._patch(self.member, self._my_url(), "")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._profile().unverified_friend_id, "")

    def test_same_users_id_in_other_org_is_accepted(self) -> None:
        other_org = Organization.objects.create(name="Friend ID Org 2")
        other_ou = OrgUser.objects.create(user=self.member, organization=other_org)
        PlayerDotaProfile.objects.create(org_user=other_ou, unverified_friend_id="777")
        for actor, url in (
            (self.member, self._my_url()),
            (self.owner, self._staff_url()),
        ):
            with self.subTest(actor=actor.username):
                resp = self._patch(actor, url, "777")
                self.assertEqual(resp.status_code, 200, resp.content)
                self.assertEqual(self._profile().unverified_friend_id, "777")

    def test_unchanged_stored_id_skips_collision_check(self) -> None:
        PlayerDotaProfile.objects.filter(org_user=self.org_user).update(
            unverified_friend_id="5150"
        )
        for actor, url in (
            (self.member, self._my_url()),
            (self.owner, self._staff_url()),
        ):
            with self.subTest(actor=actor.username):
                resp = self._patch(actor, url, "5150")
                self.assertEqual(resp.status_code, 200, resp.content)
                self.assertTrue(self._profile().pos_1)
