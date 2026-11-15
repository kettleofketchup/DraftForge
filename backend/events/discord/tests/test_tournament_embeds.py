from django.test import TestCase, override_settings


@override_settings(
    SITE_URL="https://draftforge.gg",
    DFLOGO_EMOJI_ID=None,
    DISCORD_ACTIVITY_ENABLED=False,
)
class TournamentEmbedBuildersTest(TestCase):
    def test_build_draft_link_embed(self):
        from events.discord.tournament_embeds import build_draft_link_embed

        embed = build_draft_link_embed("Monday Night Dota", "Snake", 100)
        self.assertEqual(embed["title"], "Team Draft Started")
        self.assertIn("Monday Night Dota", embed["description"])
        self.assertIn("button below", embed["description"])
        self.assertEqual(embed["author"]["name"], "DraftForge")
        self.assertEqual(
            embed["url"], "https://draftforge.gg/tournament/100/teams/draft"
        )
        self.assertEqual(embed["color"], 0x5865F2)

    def test_build_draft_link_embed_with_date(self):
        from datetime import datetime, timezone

        from events.discord.tournament_embeds import build_draft_link_embed

        dt = datetime(2026, 3, 29, 20, 0, tzinfo=timezone.utc)
        embed = build_draft_link_embed(
            "Monday Night Dota", "Snake", 100, date_played=dt
        )
        self.assertEqual(len(embed["fields"]), 2)
        self.assertEqual(embed["fields"][1]["name"], "Date / Time")

    def test_build_draft_link_components(self):
        from events.discord.tournament_embeds import build_draft_link_components

        components = build_draft_link_components(100)
        self.assertEqual(len(components), 1)
        action_row = components[0]
        self.assertEqual(action_row["type"], 1)
        btn = action_row["components"][0]
        self.assertEqual(btn["type"], 2)
        self.assertEqual(btn["style"], 5)  # Link
        self.assertEqual(btn["label"], "Open in Browser")
        self.assertEqual(btn["url"], "https://draftforge.gg/tournament/100/teams/draft")
        self.assertNotIn("emoji", btn)  # No emoji when DFLOGO_EMOJI_ID is None

    @override_settings(DFLOGO_EMOJI_ID="123456789")
    def test_build_draft_link_components_with_emoji(self):
        # Reload module to pick up new settings
        import importlib

        import events.discord.tournament_embeds as mod

        importlib.reload(mod)
        try:
            components = mod.build_draft_link_components(100)
            btn = components[0]["components"][0]
            self.assertEqual(btn["emoji"], {"name": "dflogo", "id": "123456789"})
        finally:
            importlib.reload(mod)  # Reset

    def test_build_herodraft_link_embed(self):
        from events.discord.tournament_embeds import build_herodraft_link_embed

        embed = build_herodraft_link_embed(
            "Monday Night Dota", 99, "Team Alpha", "Team Bravo"
        )
        self.assertEqual(embed["title"], "Hero Draft Ready")
        self.assertIn("Monday Night Dota", embed["description"])
        self.assertIn("Team Alpha", embed["description"])
        self.assertIn("Team Bravo", embed["description"])
        self.assertEqual(embed["url"], "https://draftforge.gg/herodraft/99")
        self.assertEqual(embed["color"], 0xED4245)

    def test_build_herodraft_link_components(self):
        from events.discord.tournament_embeds import build_herodraft_link_components

        components = build_herodraft_link_components(99)
        btn = components[0]["components"][0]
        self.assertEqual(btn["label"], "Open in Browser")
        self.assertEqual(btn["url"], "https://draftforge.gg/herodraft/99")
        self.assertEqual(btn["style"], 5)

    @override_settings(DISCORD_ACTIVITY_ENABLED=True)
    def test_team_notification_has_scoped_launch_button_and_browser_fallback(self):
        from events.discord.tournament_embeds import (
            build_draft_link_components,
            build_draft_link_embed,
        )

        buttons = build_draft_link_components(100, draft_id=42)[0]["components"]
        self.assertEqual(buttons[0]["label"], "Open in Browser")
        self.assertEqual(
            buttons[1],
            {
                "type": 2,
                "style": 1,
                "label": "Launch / Join Activity",
                "custom_id": "draft_activity:team:42",
            },
        )
        description = build_draft_link_embed("Tournament", "Snake", 100)["description"]
        self.assertIn("voice channel", description)
        self.assertIn("Open the invite", description)

    @override_settings(DISCORD_ACTIVITY_ENABLED=True)
    def test_hero_notification_has_scoped_launch_button_and_browser_fallback(self):
        from events.discord.tournament_embeds import (
            build_herodraft_link_components,
            build_herodraft_link_embed,
        )

        buttons = build_herodraft_link_components(99)[0]["components"]
        self.assertEqual(buttons[0]["style"], 5)
        self.assertEqual(buttons[1]["custom_id"], "draft_activity:hero:99")
        self.assertEqual(buttons[1]["label"], "Launch / Join Activity")
        description = build_herodraft_link_embed("Tournament", 99, "A", "B")[
            "description"
        ]
        self.assertIn("voice channel", description)

    @override_settings(DISCORD_ACTIVITY_ENABLED=True)
    def test_team_notification_without_draft_id_keeps_only_browser_button(self):
        from events.discord.tournament_embeds import build_draft_link_components

        self.assertEqual(len(build_draft_link_components(100)[0]["components"]), 1)

    def test_disabled_activity_keeps_original_notification_buttons(self):
        from events.discord.tournament_embeds import (
            build_draft_link_components,
            build_herodraft_link_components,
        )

        self.assertEqual(
            len(build_draft_link_components(100, draft_id=42)[0]["components"]), 1
        )
        self.assertEqual(len(build_herodraft_link_components(99)[0]["components"]), 1)
