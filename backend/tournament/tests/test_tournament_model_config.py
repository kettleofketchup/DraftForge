from django.conf import settings
from django.test import SimpleTestCase

from tournament.models import Game, Team, TeamLog, Tournament

MODELS = (Tournament, Team, Game, TeamLog)

CACHE_PROFILE = {"ops": "all", "timeout": 60 * 60}


class TournamentModelConfigTest(SimpleTestCase):
    def test_labels_and_tables(self) -> None:
        self.assertEqual(
            [(m._meta.label, m._meta.db_table) for m in MODELS],
            [
                ("tournament.Tournament", "app_tournament"),
                ("tournament.Team", "app_team"),
                ("tournament.Game", "app_game"),
                ("tournament.TeamLog", "app_teamlog"),
            ],
        )

    def test_m2m_tables_unchanged(self) -> None:
        tables = {
            f"{m.__name__}.{f.name}": f.remote_field.through._meta.db_table
            for m in MODELS
            for f in m._meta.local_many_to_many
        }
        self.assertEqual(
            tables,
            {
                "Tournament.users": "app_tournament_users",
                "Team.members": "app_team_members",
                "Team.dropin_members": "app_team_dropin_members",
                "Team.left_members": "app_team_left_members",
                "Team.league_users": "app_team_league_users",
            },
        )

    def test_db_columns(self) -> None:
        self.assertEqual(
            Tournament._meta.get_field("steam_league_id").column, "league_id"
        )
        self.assertEqual(Tournament._meta.get_field("league").column, "league_fk_id")

    def test_index_names(self) -> None:
        self.assertEqual(
            {m._meta.model_name: [i.name for i in m._meta.indexes] for m in MODELS},
            {
                "tournament": [
                    "app_tournam_name_8e0538_idx",
                    "app_tournam_date_pl_35179a_idx",
                    "app_tournam_state_18ca9a_idx",
                    "app_tournam_league__8406ee_idx",
                ],
                "team": [
                    "app_team_tournam_97ad87_idx",
                    "app_team_name_d8f293_idx",
                    "app_team_captain_5fcdd6_idx",
                    "app_team_deputy__d95afa_idx",
                ],
                "game": [
                    "app_game_tournam_ebb2c8_idx",
                    "app_game_league__9d936f_idx",
                    "app_game_status_635436_idx",
                    "app_game_gameid_71ac99_idx",
                    "app_game_radiant_aa1c7a_idx",
                    "app_game_dire_te_715044_idx",
                ],
                "teamlog": [
                    "app_teamlog_team_sn_55b21a_idx",
                    "app_teamlog_event_i_5a0a4b_idx",
                    "app_teamlog_tournam_019211_idx",
                ],
            },
        )

    def test_cacheops_keys(self) -> None:
        for key in ("tournament.tournament", "tournament.team", "tournament.game"):
            self.assertEqual(settings.CACHEOPS[key], CACHE_PROFILE)
        self.assertNotIn("tournament.teamlog", settings.CACHEOPS)
        self.assertFalse(
            [
                k
                for k in settings.CACHEOPS
                if k.split(".")[0] == "app" and k != "app.customuser"
            ]
        )
