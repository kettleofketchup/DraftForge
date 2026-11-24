from django.test import SimpleTestCase

from user.schemas import TournamentUserSchema


class TournamentUserSchemaDisplayNameTest(SimpleTestCase):
    def test_server_nickname_first(self) -> None:
        schema = TournamentUserSchema(
            pk=1, guildNickname="D", discordNickname="G", username="u"
        )
        self.assertEqual(schema.display_name, "D")

    def test_falls_through_blank_names(self) -> None:
        schema = TournamentUserSchema(
            pk=1, guildNickname="  ", discordNickname="G", username="u"
        )
        self.assertEqual(schema.display_name, "G")
        schema = TournamentUserSchema(pk=1, discordNickname="", username="u")
        self.assertEqual(schema.display_name, "u")

    def test_all_null(self) -> None:
        self.assertEqual(TournamentUserSchema(pk=1).display_name, "User 1")

    def test_site_nickname_between_global_name_and_username(self) -> None:
        schema = TournamentUserSchema.model_validate(
            {"pk": 1, "nickname": "Site", "discordNickname": "G", "username": "u"}
        )
        self.assertEqual(schema.display_name, "G")
        schema = TournamentUserSchema.model_validate(
            {"pk": 1, "nickname": "Site", "username": "u"}
        )
        self.assertEqual(schema.display_name, "Site")
        schema = TournamentUserSchema.model_validate(
            {"pk": 1, "guildNickname": "D", "nickname": "Site", "username": "u"}
        )
        self.assertEqual(schema.display_name, "D")
