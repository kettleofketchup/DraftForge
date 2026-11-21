from app.models import GameType
from events.discord import (
    build_announcement_embed,
    build_attendance_reminder_embed,
    build_new_event_embed,
    build_profile_reminder_embed,
    build_signup_reminder_embed,
    build_signup_update_embed,
)
from events.tests._internal_client_orm import (
    DiscordTestMixin,
    _get_event_for_task_orm,
)
from events.tests.base import EventTestCase


class _EmbedTestCase(DiscordTestMixin, EventTestCase):
    """EventTestCase + ORM-backed internal_client patches."""


class BuildAnnouncementEmbedTest(_EmbedTestCase):
    def test_uses_event_name_as_title(self):
        embed = build_announcement_embed(self.event)
        self.assertIn(self.event.name, embed["title"])

    def test_includes_scheduled_time(self):
        embed = build_announcement_embed(self.event)
        self.assertIn("description", embed)

    def test_has_color(self):
        embed = build_announcement_embed(self.event)
        self.assertIsInstance(embed["color"], int)


class BuildSignupUpdateEmbedTest(_EmbedTestCase):
    def test_includes_event_name(self):
        embed = build_signup_update_embed(self.event)
        self.assertIn(self.event.name, embed["title"])

    def test_includes_signup_count_field(self):
        embed = build_signup_update_embed(self.event)
        field_names = [f["name"] for f in embed.get("fields", [])]
        self.assertTrue(
            any("sign" in n.lower() or "player" in n.lower() for n in field_names)
        )


class BuildNewEventEmbedTest(_EmbedTestCase):
    def test_includes_event_name(self):
        embed = build_new_event_embed(self.event)
        self.assertIn(self.event.name, embed["title"])


class BuildSignupReminderEmbedTest(_EmbedTestCase):
    def test_includes_event_name(self):
        embed = build_signup_reminder_embed(self.event)
        self.assertIn(self.event.name, embed["title"])


class BuildAttendanceReminderEmbedTest(_EmbedTestCase):
    def test_includes_event_name(self):
        embed = build_attendance_reminder_embed(self.event)
        self.assertIn(self.event.name, embed["title"])


class BuildProfileReminderEmbedTest(_EmbedTestCase):
    def test_includes_event_name(self):
        embed = build_profile_reminder_embed(self.event)
        self.assertIn(self.event.name, embed["title"])

    def _reminder_for(self, **overrides: object) -> str:
        event = self.make_event(**overrides)
        task_event = _get_event_for_task_orm(event.pk)
        assert task_event is not None
        return build_profile_reminder_embed(task_event)["description"]

    def test_dota_lists_friend_id_and_verified_mmr(self) -> None:
        desc = self._reminder_for(
            game_type=GameType.DOTA2,
            require_steam_id=True,
            require_mmr_verified=True,
        )
        self.assertIn("Dota 2 Friend ID", desc)
        self.assertIn("Verified MMR", desc)
        self.assertNotIn("a complete profile", desc)

    def test_deadlock_omits_verified_mmr_and_uses_steam_wording(self) -> None:
        desc = self._reminder_for(
            game_type=GameType.DEADLOCK,
            require_steam_id=True,
            require_mmr_verified=True,
        )
        self.assertIn("Steam Friend ID", desc)
        self.assertNotIn("Verified MMR", desc)
        self.assertNotIn("Dota", desc)

    def test_lists_complete_profile_requirement(self) -> None:
        desc = self._reminder_for(require_profile_complete=True)
        self.assertIn("Complete profile", desc)

    def test_no_requirements_falls_back_to_generic_line(self) -> None:
        desc = self._reminder_for()
        self.assertIn("a complete profile", desc)


class BuildAnnouncementEmbedSignupListTest(_EmbedTestCase):
    def test_empty_signup_list(self):
        embed = build_announcement_embed(self.event)
        # Signed Up field always shown, even when empty (shows "None yet")
        signed_up = next(f for f in embed["fields"] if "Signed Up" in f["name"])
        self.assertIn("None yet", signed_up["value"])

    def test_signup_list_shows_confirmed_users(self):
        from events.constants import SignupStatus
        from events.models import EventSignup

        EventSignup.objects.create(
            event=self.event, user=self.user, status=SignupStatus.CONFIRMED
        )
        embed = build_announcement_embed(self.event)
        field_names = [f["name"] for f in embed.get("fields", [])]
        self.assertTrue(any("Signed Up" in n for n in field_names))

    def test_signup_list_shows_status_icons(self):
        from events.constants import SignupStatus
        from events.models import EventSignup

        EventSignup.objects.create(
            event=self.event, user=self.user, status=SignupStatus.CONFIRMED
        )
        embed = build_announcement_embed(self.event)
        signed_up_field = next(f for f in embed["fields"] if "Signed Up" in f["name"])
        self.assertIn("\u2705", signed_up_field["value"])

    def test_waitlisted_in_separate_field(self):
        from app.models import CustomUser, PositionsModel
        from events.constants import SignupStatus
        from events.discord.embeds import build_announcement_v2
        from events.models import EventSignup

        self.event.max_players = 1
        self.event.save()
        EventSignup.objects.create(
            event=self.event, user=self.user, status=SignupStatus.CONFIRMED
        )
        pos = PositionsModel.objects.create()
        user2 = CustomUser.objects.create(username="waitlisted_user", positions=pos)
        EventSignup.objects.create(
            event=self.event,
            user=user2,
            status=SignupStatus.WAITLISTED,
            waitlist_position=1,
        )
        # Use build_announcement_v2 which includes the Waitlisted field
        result = build_announcement_v2(self.event)
        content_embed = result["embeds"][1]
        field_names = [f["name"] for f in content_embed["fields"]]
        self.assertTrue(any("Waitlisted" in n for n in field_names))
        waitlist_field = next(
            f for f in content_embed["fields"] if "Waitlisted" in f["name"]
        )
        self.assertIn("waitlisted_user", waitlist_field["value"])

    def test_signup_fields_are_inline(self):
        from events.constants import SignupStatus
        from events.models import EventSignup

        EventSignup.objects.create(
            event=self.event, user=self.user, status=SignupStatus.CONFIRMED
        )
        embed = build_announcement_embed(self.event)
        signed_up_field = next(f for f in embed["fields"] if "Signed Up" in f["name"])
        self.assertTrue(signed_up_field["inline"])


class ReminderEmbedSignupCountTest(_EmbedTestCase):
    """Regression tests for issue #188 — reminder embeds showed 0/∞ instead of
    actual signup count because _build_reminder_embed and
    build_signup_reminder_embed read event.signup_count via getattr (a
    serializer-computed field, not a model attribute).  Fix: use the existing
    _signup_counts(event) helper that queries EventSignup.status directly.
    """

    def _add_signup(self, status, index):
        from app.models import CustomUser, PositionsModel
        from events.models import EventSignup

        pos = PositionsModel.objects.create()
        u = CustomUser.objects.create_user(
            username=f"reminder_signup_user_{self.event.pk}_{index}",
        )
        u.positions = pos
        u.save()
        return EventSignup.objects.create(event=self.event, user=u, status=status)

    def test_signup_reminder_shows_active_signup_count(self):
        """issue #188: build_signup_reminder_embed must show real signup count."""
        from events.constants import SignupStatus

        for i in range(13):
            self._add_signup(status=SignupStatus.APPROVED, index=i)

        result = build_signup_reminder_embed(self.event)

        signups_field = next(
            f for f in result["embed"]["fields"] if f["name"] == "Signups"
        )
        self.assertEqual(signups_field["value"], "**13/10** players")
        self.assertIn("13/10", result["embed"]["description"])

    def test_reminder_embed_excludes_cancelled_and_waitlisted(self):
        """Active count must exclude cancelled, rejected, waitlisted signups."""
        from events.constants import SignupStatus

        for i in range(5):
            self._add_signup(status=SignupStatus.APPROVED, index=i)
        self._add_signup(status=SignupStatus.CANCELLED, index=10)
        self._add_signup(status=SignupStatus.REJECTED, index=11)
        self._add_signup(status=SignupStatus.WAITLISTED, index=12)

        result = build_signup_reminder_embed(self.event)
        signups_field = next(
            f for f in result["embed"]["fields"] if f["name"] == "Signups"
        )
        self.assertEqual(signups_field["value"], "**5/10** players")
