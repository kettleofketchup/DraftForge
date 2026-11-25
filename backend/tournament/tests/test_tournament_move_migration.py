from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import connection, models
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader
from django.test import TransactionTestCase
from django.utils import timezone
from structlog.testing import capture_logs

from app.models import CustomUser
from league.models import League, LeagueUser
from org.models import Organization, OrgUser
from tournament.models import Game, Team, TeamLog, Tournament
from tournament.models.team_log import TeamLogAction, TeamLogVia

TOURNAMENT_MODELS = ("tournament", "team", "game", "teamlog")
MOVED_TABLES = ("app_tournament", "app_team", "app_game", "app_teamlog")
M2M_TABLES = (
    "app_tournament_users",
    "app_team_members",
    "app_team_dropin_members",
    "app_team_left_members",
    "app_team_league_users",
)
REFERRING_TABLES = (
    "app_draft",
    "app_draftoptions",
    "app_draftteam",
    "app_herodraft",
    "app_leaguematch",
    "bracket_bracketslot",
    "bracket_tournamentbracket",
    "discordbot_discordtournamentlog",
    "draft_herodraftchatmembership",
    "draft_herodraftchatmessage",
    "events_event",
    "lobby_gamelobby",
    "org_eventcaptain",
    "steam_gamematchsuggestion",
)
BEFORE_MOVE: list[tuple[str, str | None]] = [
    ("app", "0114_copy_profile_friend_ids"),
    ("bracket", "0002_alter_bracketslot_bracket_and_more"),
    ("discordbot", "0014_retarget_draft_activity_teamdraft"),
    ("draft", "0005_herodraft_chat_withdraw_suggestion"),
    ("events", "0039_alter_signupledgerentry_action"),
    ("league", "0003_move_league_models_from_app"),
    ("lobby", "0004_gamelobby_password"),
    ("org", "0021_leadership_release_gate"),
    ("steam", "0008_gamematchsuggestion_tier"),
    ("tournament", None),
]
MOVE_MIGRATION = ("app", "0115_move_tournament_models_to_tournament")
RETARGETS = (
    ("tournament", "0001_initial"),
    ("bracket", "0003_retarget_tournament_models"),
    ("discordbot", "0015_retarget_tournament_models"),
    ("draft", "0006_retarget_tournament_models"),
    ("events", "0040_retarget_tournament_to_tournament"),
    ("league", "0004_retarget_leaguematch_game"),
    ("lobby", "0005_retarget_tournament_models"),
    ("org", "0022_retarget_tournament_models"),
    ("steam", "0009_retarget_tournament_models"),
)
AFTER_MOVE: list[tuple[str, str | None]] = [
    ("events", "0040_retarget_tournament_to_tournament"),
]
MIGRATED_APPS = (
    "app",
    "tournament",
    "bracket",
    "discordbot",
    "draft",
    "events",
    "league",
    "lobby",
    "org",
    "steam",
)
APP = "app"
TOURNAMENT = "tournament"


def _schema_rows() -> list[tuple[str, str, str, str | None]]:
    tables = MOVED_TABLES + M2M_TABLES + REFERRING_TABLES
    with connection.cursor() as cursor:
        placeholders = ",".join("%s" for _ in tables)
        cursor.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            f"WHERE tbl_name IN ({placeholders}) ORDER BY tbl_name, type, name",
            list(tables),
        )
        return cursor.fetchall()


def _row_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    with connection.cursor() as cursor:
        for table in MOVED_TABLES + M2M_TABLES:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            counts[table] = cursor.fetchone()[0]
    return counts


class TournamentMoveMigrationTests(TransactionTestCase):
    def tearDown(self) -> None:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        ContentType.objects.clear_cache()
        super().tearDown()

    def _migrate(self, targets: list[tuple[str, str | None]]) -> None:
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        ContentType.objects.clear_cache()

    def _forward(self) -> None:
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
        ContentType.objects.clear_cache()

    def _labels(self, ids: dict[str, int]) -> dict[str, tuple[str, str]]:
        return {
            key: tuple(
                ContentType.objects.filter(pk=pk).values_list("app_label", "model")[0]
            )
            for key, pk in ids.items()
        }

    def _grant(
        self, content_type_id: int, model: str, suffix: str
    ) -> tuple[Permission, CustomUser, Group]:
        perm, _ = Permission.objects.get_or_create(
            codename=f"change_{model}",
            content_type_id=content_type_id,
            defaults={"name": f"Can change {model}"},
        )
        user = CustomUser.objects.create_user(username=f"tournament_perm_{suffix}")
        group = Group.objects.create(name=f"tournament_perm_group_{suffix}")
        user.user_permissions.add(perm)
        group.permissions.add(perm)
        return perm, user, group

    def _assert_grant(
        self, perm: Permission, user: CustomUser, group: Group, content_type_id: int
    ) -> None:
        perm.refresh_from_db()
        self.assertEqual(perm.content_type_id, content_type_id)
        self.assertTrue(user.user_permissions.filter(pk=perm.pk).exists())
        self.assertTrue(group.permissions.filter(pk=perm.pk).exists())

    def _seed(self, owner: CustomUser) -> Tournament:
        org = Organization.objects.create(name="Tournament Move Org", owner=owner)
        league = League.objects.create(
            name="Tournament Move League", organization=org, steam_league_id=99555
        )
        captain = CustomUser.objects.create_user(username="tournament_move_captain")
        dropin = CustomUser.objects.create_user(username="tournament_move_dropin")
        left = CustomUser.objects.create_user(username="tournament_move_left")
        org_user = OrgUser.objects.create(user=captain, organization=org)
        league_user = LeagueUser.objects.create(
            user=captain, org_user=org_user, league=league
        )
        tournament = Tournament.objects.create(
            name="Tournament Move Tournament", date_played=timezone.now(), league=league
        )
        tournament.users.add(captain)
        radiant = Team.objects.create(
            tournament=tournament, name="Tournament Move Radiant", captain=captain
        )
        radiant.members.add(captain)
        radiant.dropin_members.add(dropin)
        radiant.left_members.add(left)
        radiant.league_users.add(league_user)
        dire = Team.objects.create(tournament=tournament, name="Tournament Move Dire")
        tournament.winning_team = radiant
        tournament.save()
        Game.objects.create(
            tournament=tournament,
            league=league,
            radiant_team=radiant,
            dire_team=dire,
            winning_team=radiant,
        )
        TeamLog.objects.create(
            team=radiant,
            tournament_id=tournament.pk,
            team_name=radiant.name,
            actor=owner,
            via=TeamLogVia.WEB,
            action=TeamLogAction.RENAME,
        )
        return tournament

    def _assert_links(self, tournament: Tournament) -> None:
        tournament.refresh_from_db()
        radiant = Team.objects.get(name="Tournament Move Radiant")
        self.assertEqual(tournament.winning_team_id, radiant.pk)
        game = Game.objects.get(tournament=tournament)
        self.assertEqual(game.radiant_team_id, radiant.pk)
        self.assertEqual(game.winning_team_id, radiant.pk)
        self.assertEqual(
            list(radiant.members.values_list("username", flat=True)),
            ["tournament_move_captain"],
        )
        self.assertEqual(TeamLog.objects.get().team_id, radiant.pk)

    def test_back_forward_back_forward_no_ddl(self) -> None:
        ids = {
            model: ContentType.objects.get_or_create(app_label=TOURNAMENT, model=model)[
                0
            ].pk
            for model in TOURNAMENT_MODELS
        }
        perm, user, group = self._grant(ids["team"], "team", "move")
        tournament = self._seed(user)
        counts = _row_counts()
        self.assertEqual(
            counts,
            {
                "app_tournament": 1,
                "app_team": 2,
                "app_game": 1,
                "app_teamlog": 1,
                "app_tournament_users": 1,
                "app_team_members": 1,
                "app_team_dropin_members": 1,
                "app_team_left_members": 1,
                "app_team_league_users": 1,
            },
        )
        schema_leaf = _schema_rows()
        self._migrate(AFTER_MOVE)
        schema_before = _schema_rows()
        self._forward()
        self.assertEqual(
            {row[2] for row in schema_before},
            set(MOVED_TABLES + M2M_TABLES + REFERRING_TABLES),
        )
        self.assertTrue(any(row[0] == "index" for row in schema_before))

        for _ in range(2):
            self._migrate(BEFORE_MOVE)

            self.assertEqual(
                self._labels(ids), {m: (APP, m) for m in TOURNAMENT_MODELS}
            )
            self._assert_grant(perm, user, group, ids["team"])
            self.assertEqual(_row_counts(), counts)
            self.assertEqual(_schema_rows(), schema_before)

            self._forward()

            self.assertEqual(
                self._labels(ids), {m: (TOURNAMENT, m) for m in TOURNAMENT_MODELS}
            )
            self._assert_grant(perm, user, group, ids["team"])
            self.assertEqual(_row_counts(), counts)
            self.assertEqual(_schema_rows(), schema_leaf)
            self._assert_links(tournament)

    def test_grants_follow_relabelled_contenttypes(self) -> None:
        team_ct = ContentType.objects.get_or_create(app_label=TOURNAMENT, model="team")[
            0
        ]
        perm, user, _ = self._grant(team_ct.pk, "team", "grant")
        self.assertTrue(
            CustomUser.objects.get(pk=user.pk).has_perm("tournament.change_team")
        )

        self._migrate(BEFORE_MOVE)
        self.assertEqual(self._labels({"t": team_ct.pk}), {"t": (APP, "team")})
        self.assertTrue(CustomUser.objects.get(pk=user.pk).has_perm("app.change_team"))

        self._forward()
        self.assertEqual(self._labels({"t": team_ct.pk}), {"t": (TOURNAMENT, "team")})
        perm.refresh_from_db()
        self.assertEqual(perm.content_type_id, team_ct.pk)
        self.assertTrue(
            CustomUser.objects.get(pk=user.pk).has_perm("tournament.change_team")
        )

    def test_duplicate_contenttype_skipped_both_directions(self) -> None:
        original, _ = ContentType.objects.get_or_create(
            app_label=TOURNAMENT, model="team"
        )
        perm, user, group = self._grant(original.pk, "team", "dup")

        self._migrate(BEFORE_MOVE)
        self.assertEqual(self._labels({"o": original.pk}), {"o": (APP, "team")})
        duplicate = ContentType.objects.create(app_label=TOURNAMENT, model="team")
        expected = {"o": (APP, "team"), "d": (TOURNAMENT, "team")}
        ids = {"o": original.pk, "d": duplicate.pk}

        with capture_logs() as forward_logs:
            self._forward()
        self.assertEqual(self._labels(ids), expected)
        self._assert_grant(perm, user, group, original.pk)

        with capture_logs() as reverse_logs:
            self._migrate(BEFORE_MOVE)
        self.assertEqual(self._labels(ids), expected)
        self._assert_grant(perm, user, group, original.pk)

        skipped = [
            (entry["model"], entry["direction"])
            for entry in forward_logs + reverse_logs
            if entry["event"] == "contenttype_relabel_skipped"
        ]
        self.assertEqual(
            skipped, [("team", "app->tournament"), ("team", "tournament->app")]
        )

    def test_retargets_precede_app_0115(self) -> None:
        plan = MigrationLoader(connection).graph.forwards_plan(MOVE_MIGRATION)
        for retarget in RETARGETS:
            self.assertIn(retarget, plan)

    def test_one_leaf_per_app(self) -> None:
        leaves = MigrationLoader(None, ignore_no_migrations=True).graph.leaf_nodes()
        for app_label in MIGRATED_APPS:
            self.assertEqual(
                len([node for node in leaves if node[0] == app_label]),
                1,
                app_label,
            )

    def test_state_index_names_exist_in_db(self) -> None:
        indexed: tuple[type[models.Model], ...] = (Tournament, Team, Game, TeamLog)
        with connection.cursor() as cursor:
            for model in indexed:
                constraints = connection.introspection.get_constraints(
                    cursor, model._meta.db_table
                )
                self.assertTrue(model._meta.indexes, model.__name__)
                for index in model._meta.indexes:
                    self.assertIn(index.name, constraints, model.__name__)
