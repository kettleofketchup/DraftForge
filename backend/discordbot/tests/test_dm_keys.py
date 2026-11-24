from django.test import SimpleTestCase

from discordbot.dm_context import LeadershipReviewContext, validate_context
from discordbot.dm_keys import (
    KEY_BUILDERS,
    leadership_review_key,
    lobby_info_key,
    signup_confirmation_key,
    signup_reminder_key,
    test_notification_key,
    tournament_draft_link_key,
    tournament_herodraft_link_key,
)
from discordbot.models import DMKind


class DMKeyTests(SimpleTestCase):
    def test_signup_reminder_key(self) -> None:
        self.assertEqual(
            signup_reminder_key(event_id=3, user_pk=4),
            "signup_reminder:event:3:user:4",
        )

    def test_tournament_draft_link_key(self) -> None:
        self.assertEqual(
            tournament_draft_link_key(task_id="t", discord_id="d"),
            "tournament_draft_link:run:t:discord:d",
        )

    def test_tournament_herodraft_link_key(self) -> None:
        self.assertEqual(
            tournament_herodraft_link_key(task_id="t", discord_id="d"),
            "tournament_herodraft_link:run:t:discord:d",
        )

    def test_lobby_info_key(self) -> None:
        self.assertEqual(
            lobby_info_key(game_lobby_id=5, task_id="t", discord_id="d"),
            "lobby_info:lobby:5:run:t:discord:d",
        )

    def test_signup_confirmation_key(self) -> None:
        self.assertEqual(
            signup_confirmation_key(interaction_id=99),
            "signup_confirmation:interaction:99",
        )

    def test_leadership_review_key(self) -> None:
        self.assertEqual(
            leadership_review_key(snapshot_id=7, rater_org_user_id=9, part=2),
            "leadership_review:snapshot:7:rater:9:part:2",
        )

    def test_test_notification_key(self) -> None:
        self.assertEqual(
            test_notification_key(event_pk=1, discord_id="d", request_id="r"),
            "test_notification:event:1:discord:d:req:r",
        )

    def test_every_kind_has_builder(self) -> None:
        self.assertEqual(set(KEY_BUILDERS), set(DMKind))


class DMContextTests(SimpleTestCase):
    def test_context_rejects_unknown_keys(self) -> None:
        with self.assertRaises(ValueError):
            validate_context(DMKind.LOBBY_INFO, {"side": "radiant", "password": "x"})
        with self.assertRaises(ValueError):
            validate_context(DMKind.LOBBY_INFO, {"side": "green"})
        self.assertEqual(
            validate_context(DMKind.LOBBY_INFO, {"side": "dire"}), {"side": "dire"}
        )

    def test_empty_context_for_test_notification(self) -> None:
        self.assertEqual(validate_context(DMKind.TEST_NOTIFICATION, {}), {})
        with self.assertRaises(ValueError):
            validate_context(DMKind.TEST_NOTIFICATION, {"body": "hi"})

    def test_leadership_context_has_no_rater(self) -> None:
        self.assertEqual(
            set(LeadershipReviewContext.model_fields),
            {"snapshot_id", "part", "parts", "trait_ids"},
        )

    def test_leadership_context_round_trip(self) -> None:
        data = {"snapshot_id": 1, "part": 1, "parts": 2, "trait_ids": [3, 4]}
        self.assertEqual(validate_context(DMKind.LEADERSHIP_REVIEW, data), data)

    def test_signup_confirmation_result_choices(self) -> None:
        ok = {"result": "tentative", "interaction_id": "5"}
        self.assertEqual(validate_context(DMKind.SIGNUP_CONFIRMATION, ok), ok)
        with self.assertRaises(ValueError):
            validate_context(
                DMKind.SIGNUP_CONFIRMATION, {"result": "maybe", "interaction_id": "5"}
            )

    def test_legacy_flag_backfill_only(self) -> None:
        data = {"legacy_kind_unknown": True}
        with self.assertRaises(ValueError):
            validate_context(DMKind.TOURNAMENT_DRAFT_LINK, data)
        self.assertEqual(
            validate_context(DMKind.TOURNAMENT_DRAFT_LINK, data, backfill=True), data
        )
