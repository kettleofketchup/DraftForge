from django.test import SimpleTestCase

from app.models import Tournament
from league.models import League, LeagueLog, LeagueUser


class LeagueModelConfigTests(SimpleTestCase):
    def test_m2m_tables_and_reverse_fk(self) -> None:
        self.assertEqual(
            League._meta.get_field("admins").remote_field.through._meta.db_table,
            "app_league_admins",
        )
        self.assertEqual(
            League._meta.get_field("staff").remote_field.through._meta.db_table,
            "app_league_staff",
        )
        self.assertIs(LeagueUser._meta.get_field("league").related_model, League)
        tournament_league = Tournament._meta.get_field("league")
        self.assertEqual(tournament_league.db_column, "league_fk_id")
        self.assertIs(tournament_league.related_model, League)

    def test_index_names(self) -> None:
        self.assertEqual(
            [index.name for index in League._meta.indexes],
            ["app_league_name_844732_idx", "app_league_created_a10ab0_idx"],
        )
        self.assertEqual(
            [index.name for index in LeagueLog._meta.indexes],
            ["app_leaguel_league__800628_idx"],
        )
