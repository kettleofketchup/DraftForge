from django.test import TestCase
from django.utils import timezone


class DiscordTournamentLogTest(TestCase):
    def setUp(self):
        from app.models import Tournament

        self.tournament = Tournament.objects.create(
            name="Test", state="future", date_played=timezone.now()
        )

    def test_create_log(self):
        from discordbot.models import DiscordTournamentLog

        log_entry = DiscordTournamentLog.objects.create(
            tournament=self.tournament,
            notification_type="draft_link",
            message="Sent to 5/8",
            recipient_count=5,
        )
        self.assertTrue(log_entry.success)
        self.assertEqual(log_entry.notification_type, "draft_link")

    def test_log_ordering_newest_first(self):
        from discordbot.models import DiscordTournamentLog

        log1 = DiscordTournamentLog.objects.create(
            tournament=self.tournament,
            notification_type="draft_link",
            message="First",
        )
        log2 = DiscordTournamentLog.objects.create(
            tournament=self.tournament,
            notification_type="herodraft_link",
            message="Second",
        )
        logs = list(DiscordTournamentLog.objects.filter(tournament=self.tournament))
        self.assertEqual(logs[0].pk, log2.pk)


class DiscordTournamentConfigFieldsTest(TestCase):
    def test_tournament_has_config_fields(self):
        from app.models import Tournament

        t = Tournament()
        self.assertFalse(t.auto_create_hero_drafts)
        self.assertFalse(t.discord_send_draft_link)
        self.assertFalse(t.discord_send_herodraft_link)

    def test_event_has_tournament_discord_fields(self):
        from events.models import Event

        self.assertTrue(hasattr(Event, "discord_send_draft_link"))
        self.assertTrue(hasattr(Event, "discord_send_herodraft_link"))

    def test_event_repeater_has_fields(self):
        from events.models import EventRepeater

        self.assertTrue(hasattr(EventRepeater, "discord_send_draft_link"))
        self.assertTrue(hasattr(EventRepeater, "auto_create_hero_drafts"))

    def test_org_event_defaults_has_fields(self):
        from events.models import OrgEventDefaults

        self.assertTrue(hasattr(OrgEventDefaults, "auto_create_hero_drafts"))
        self.assertTrue(hasattr(OrgEventDefaults, "discord_send_draft_link"))
