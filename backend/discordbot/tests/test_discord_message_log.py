from django.test import TestCase


class DiscordMessageLogModelTest(TestCase):
    def test_create_log_entry(self):
        """DiscordMessageLog can be created with required fields."""
        from discordbot.models import DiscordMessageLog

        log_entry = DiscordMessageLog.objects.create(
            channel_id="123456789012345678",
            embed_data={
                "title": "Test",
                "description": "Test embed",
                "color": 0x00FF00,
            },
            source="event_announcement",
            source_id=42,
        )
        self.assertEqual(log_entry.channel_id, "123456789012345678")
        self.assertEqual(log_entry.source, "event_announcement")
        self.assertFalse(log_entry.success)
        self.assertIsNone(log_entry.discord_message_id)

    def test_log_entry_with_response(self):
        """DiscordMessageLog can store Discord API response data."""
        from discordbot.models import DiscordMessageLog

        log_entry = DiscordMessageLog.objects.create(
            channel_id="123456789012345678",
            embed_data={"title": "Test"},
            source="signup_update",
            source_id=7,
            discord_message_id="999888777666555444",
            status_code=200,
            response_data={"id": "999888777666555444", "type": 0},
            success=True,
        )
        self.assertTrue(log_entry.success)
        self.assertEqual(log_entry.discord_message_id, "999888777666555444")
        self.assertEqual(log_entry.status_code, 200)

    def test_log_str(self):
        """DiscordMessageLog __str__ returns readable representation."""
        from discordbot.models import DiscordMessageLog

        log_entry = DiscordMessageLog.objects.create(
            channel_id="123",
            embed_data={"title": "Test"},
            source="event_announcement",
        )
        self.assertIn("event_announcement", str(log_entry))
