"""Byte-for-byte round-trip guard for the custom_id codecs (#268).

SimpleTestCase so it runs under the canonical `manage.py test` runner.
These literals MUST match the strings emitted by the pre-refactor
components.py, or persistent components on posted messages break.
"""

from django.test import SimpleTestCase

from discordbot import custom_ids as cid


class CustomIdRoundTripTest(SimpleTestCase):
    def test_simple_prefixes_byte_for_byte(self):
        cases = [
            (cid.SignupId(event_id=42), "event_signup:42"),
            (cid.TentativeId(event_id=42), "event_tentative:42"),
            (cid.DeclineId(event_id=42), "event_decline:42"),
            (cid.NotifyId(event_id=42), "event_notify:42"),
            (cid.SignupFriendId(event_id=7), "signup_friend_id:7"),
            (cid.SignupRankStatusId(event_id=7), "signup_rank_status:7"),
            (cid.SignupDeadlockRankId(event_id=7), "signup_deadlock_rank:7"),
            (cid.SignupDeadlockDateId(event_id=7), "signup_deadlock_date:7"),
            (cid.PosConfirmId(event_id=9), "pos_confirm:9"),
            (cid.RankStatusId(event_id=9), "rank_status:9"),
            (cid.RankMedalId(event_id=9), "rank_medal:9"),
            (cid.BattleCupTierId(event_id=9), "bcup_tier:9"),
        ]
        for obj, wire in cases:
            with self.subTest(wire=wire):
                self.assertEqual(obj.encode(), wire)
                self.assertTrue(type(obj).matches(wire))
                self.assertEqual(type(obj).decode(wire).event_id, obj.event_id)

    def test_pos_select_slot_before_colon(self):
        obj = cid.PosSelectId(event_id=14, slot=2)
        self.assertEqual(obj.encode(), "pos_select_2:14")
        self.assertTrue(cid.PosSelectId.matches("pos_select_2:14"))
        d = cid.PosSelectId.decode("pos_select_3:7")
        self.assertEqual((d.event_id, d.slot), (7, 3))

    def test_rank_star_carries_medal(self):
        obj = cid.RankStarId(event_id=5, medal="Crusader")
        self.assertEqual(obj.encode(), "rank_star:5:Crusader")
        self.assertEqual(
            cid.RankStarId.decode("rank_star:5:Crusader").medal, "Crusader"
        )

    def test_screenshot_codecs(self):
        self.assertEqual(
            cid.ScreenshotUploadId(event_id=1, screenshot_type="rank").encode(),
            "screenshot_upload:1:rank",
        )
        self.assertEqual(
            cid.ScreenshotFileId(event_id=1, screenshot_type="battlecup").encode(),
            "screenshot_file:1:battlecup",
        )
        self.assertEqual(
            cid.ScreenshotUrlId(event_id=1, screenshot_type="rank").encode(),
            "screenshot_url:1:rank",
        )
        self.assertEqual(
            cid.ScreenshotUploadId.decode("screenshot_upload:1:rank").screenshot_type,
            "rank",
        )

    def test_decode_malformed_raises_valueerror(self):
        with self.assertRaises(ValueError):
            cid.SignupId.decode("event_signup:notanint")
        with self.assertRaises(ValueError):
            cid.RankStarId.decode("rank_star:5")  # missing medal segment

    def test_missing_prefix_subclass_fails_at_definition(self):
        with self.assertRaises(TypeError):

            class _Bad(cid.CustomId):  # no PREFIX
                pass

    def test_signup_tag_prefixes_cover_all_codecs(self):
        self.assertEqual(
            cid.SIGNUP_TAG_PREFIXES, frozenset(c.PREFIX for c in cid.ALL_CODECS)
        )
        # spot-check the irregular ones normalize to the bare prefix
        self.assertIn("pos_select", cid.SIGNUP_TAG_PREFIXES)
        self.assertIn("screenshot_url", cid.SIGNUP_TAG_PREFIXES)
