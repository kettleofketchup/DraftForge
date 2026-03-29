from django.test import TestCase, override_settings


@override_settings(SITE_URL="https://draftforge.gg")
class TournamentEmbedBuildersTest(TestCase):
    def test_build_draft_link_embed(self):
        from events.discord.tournament_embeds import build_draft_link_embed

        embed = build_draft_link_embed("Monday Night Dota", "Snake", 42)
        self.assertEqual(embed["title"], "Team Draft Started")
        self.assertIn("Monday Night Dota", embed["description"])
        self.assertEqual(embed["author"]["name"], "DraftForge")
        self.assertIn("DFLogo.png", embed["author"]["icon_url"])
        self.assertIn("DFLogo.png", embed["thumbnail"]["url"])
        self.assertEqual(embed["url"], "https://draftforge.gg/draft/42")
        self.assertEqual(embed["color"], 0x5865F2)

    def test_build_draft_link_components(self):
        from events.discord.tournament_embeds import build_draft_link_components

        components = build_draft_link_components(42)
        self.assertEqual(len(components), 1)
        action_row = components[0]
        self.assertEqual(action_row["type"], 1)  # Action Row
        button = action_row["components"][0]
        self.assertEqual(button["type"], 2)  # Button
        self.assertEqual(button["style"], 5)  # Link
        self.assertEqual(button["label"], "Join Draft")
        self.assertEqual(button["url"], "https://draftforge.gg/draft/42")

    def test_build_herodraft_link_embed(self):
        from events.discord.tournament_embeds import build_herodraft_link_embed

        embed = build_herodraft_link_embed(
            "Monday Night Dota", 99, "Team Alpha", "Team Bravo"
        )
        self.assertEqual(embed["title"], "Hero Draft Ready")
        self.assertIn("Monday Night Dota", embed["description"])
        self.assertEqual(embed["fields"][0]["value"], "Team Alpha vs Team Bravo")
        self.assertEqual(embed["url"], "https://draftforge.gg/herodraft/99")
        self.assertEqual(embed["color"], 0xED4245)

    def test_build_herodraft_link_components(self):
        from events.discord.tournament_embeds import build_herodraft_link_components

        components = build_herodraft_link_components(99)
        button = components[0]["components"][0]
        self.assertEqual(button["label"], "Join Hero Draft")
        self.assertEqual(button["url"], "https://draftforge.gg/herodraft/99")
        self.assertEqual(button["style"], 5)
