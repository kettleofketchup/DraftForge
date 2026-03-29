from django.test import TestCase


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
