"""Byte-for-byte round-trip guard for the custom_id codecs (#268).

SimpleTestCase so it runs under the canonical `manage.py test` runner.
These literals MUST match the strings emitted by the pre-refactor
components.py, or persistent components on posted messages break.
"""

from django.test import SimpleTestCase

from discordbot import custom_ids as cid
from discordbot.log_context import parse_event_id, resolve_tags


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

    def test_matching_but_undecodable_ids(self) -> None:
        cases: list[tuple[str, type[cid.CustomId]]] = [
            ("event_signup:abc", cid.SignupId),
            ("event_tentative:abc", cid.TentativeId),
            ("event_decline:abc", cid.DeclineId),
            ("event_notify:abc", cid.NotifyId),
            ("pos_select_x:5", cid.PosSelectId),
            ("pos_select_1", cid.PosSelectId),
        ]
        for raw, codec in cases:
            with self.subTest(raw=raw):
                self.assertTrue(codec.matches(raw))
                with self.assertRaises(ValueError):
                    codec.decode(raw)

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


class LeadershipScoreIdTest(SimpleTestCase):
    def test_lr_round_trip(self) -> None:
        obj = cid.LeadershipScoreId(snapshot_id=12, trait_id=34, score=5)
        self.assertEqual(obj.encode(), "lr:12:34:5")
        self.assertTrue(cid.LeadershipScoreId.matches("lr:12:34:5"))
        self.assertEqual(cid.LeadershipScoreId.decode("lr:12:34:5"), obj)
        self.assertTrue(obj.encode().startswith(cid.LEADERSHIP_REVIEW_PREFIX))

    def test_lr_bounds(self) -> None:
        for raw in ("lr:1:2:0", "lr:1:2:6", "lr:0:2:3", "lr:1:0:3", "lr:-1:2:3"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                cid.LeadershipScoreId.decode(raw)

    def test_lr_malformed(self) -> None:
        for raw in ("lr:", "lr:1:2", "lr:1:2:3:4", "lr:a:2:3", "lr:1:2:x", "xr:1:2:3"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                cid.LeadershipScoreId.decode(raw)
        self.assertFalse(cid.LeadershipScoreId.matches("lrx:1:2:3"))
        self.assertFalse(cid.LeadershipScoreId.matches("event_signup:1"))

    def test_lr_not_in_all_codecs(self) -> None:
        self.assertNotIn(cid.LeadershipScoreId, cid.ALL_CODECS)
        self.assertNotIn("lr", cid.SIGNUP_TAG_PREFIXES)
        self.assertFalse(issubclass(cid.LeadershipScoreId, cid.CustomId))

    def test_lr_log_tags(self) -> None:
        self.assertEqual(resolve_tags("lr:1:2:3"), ["leadership", "review"])
        self.assertIsNone(parse_event_id("lr:1:2:3"))
