from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import connection, models
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader
from django.test import TransactionTestCase
from django.utils import timezone
from structlog.testing import capture_logs

from app.models import CustomUser
from events.models import Event
from league.models import League, LeagueLog, LeagueUser
from league.models_rating import LeagueMatch, LeagueMatchParticipant, LeagueRating
from org.models import Organization, OrgUser
from tournament.models import Game, Tournament

LEAGUE_MODELS = (
    "league",
    "leaguerating",
    "leaguematch",
    "leaguematchparticipant",
    "leaguelog",
)
MOVED_TABLES = (
    "app_league",
    "app_league_admins",
    "app_league_staff",
    "app_leaguerating",
    "app_leaguematch",
    "app_leaguematchparticipant",
    "app_leaguelog",
)
REFERRING_TABLES = (
    "app_tournament",
    "app_game",
    "league_leagueuser",
    "app_organization",
    "events_event",
    "events_eventrepeater",
    "events_orgeventdefaults",
)
BEFORE_MOVE = [
    ("app", "0111_move_organization_models_to_org"),
    ("league", "0002_populate_league_users"),
    ("org", "0016_backfill_org_user_game_mmr"),
    ("events", "0035_retarget_organization_to_org"),
]
MOVE_MIGRATION = ("app", "0112_move_league_models_to_league")
RETARGETS = (
    ("league", "0003_move_league_models_from_app"),
    ("org", "0017_retarget_default_league_to_league"),
    ("events", "0036_retarget_tournament_league_to_league"),
)
AFTER_MOVE = [MOVE_MIGRATION, *RETARGETS]
MIGRATED_APPS = ("app", "league", "org", "events")
APP = "app"
LEAGUE = "league"


def _schema_rows() -> list[tuple[str, str, str, str | None]]:
    tables = MOVED_TABLES + REFERRING_TABLES
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
        for table in MOVED_TABLES + ("league_leagueuser",):
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            counts[table] = cursor.fetchone()[0]
    return counts


class LeagueMoveMigrationTests(TransactionTestCase):
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
        user = CustomUser.objects.create_user(username=f"league_perm_user_{suffix}")
        group = Group.objects.create(name=f"league_perm_group_{suffix}")
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

    def _seed(self, owner: CustomUser) -> League:
        org = Organization.objects.create(name="League Move Org", owner=owner)
        admin = CustomUser.objects.create_user(username="league_move_admin")
        staff = CustomUser.objects.create_user(username="league_move_staff")
        player = CustomUser.objects.create_user(username="league_move_player")
        league = League.objects.create(
            name="League Move League", organization=org, steam_league_id=99222
        )
        league.admins.add(admin)
        league.staff.add(staff)
        org.default_league = league
        org.save()
        org_user = OrgUser.objects.create(user=player, organization=org)
        LeagueUser.objects.create(user=player, org_user=org_user, league=league)
        tournament = Tournament.objects.create(
            name="League Move Tournament", date_played=timezone.now(), league=league
        )
        game = Game.objects.create(tournament=tournament, league=league)
        rating = LeagueRating.objects.create(league=league, player=player)
        match = LeagueMatch.objects.create(
            league=league, game=game, played_at=timezone.now()
        )
        LeagueMatchParticipant.objects.create(
            match=match,
            player=player,
            player_rating=rating,
            team_side="radiant",
            mmr_at_match=3000,
            elo_before=3000.0,
            elo_after=3016.0,
            k_factor_used=32.0,
            is_winner=True,
            delta=16.0,
        )
        LeagueLog.objects.create(
            league=league, actor=owner, action="add_admin", target_user=admin
        )
        Event.objects.create(
            organization=org,
            name="League Move Event",
            scheduled_at=timezone.now(),
            created_by=owner,
            tournament_league=league,
        )
        return league

    def _assert_links(self, league: League) -> None:
        self.assertEqual(
            Organization.objects.get(name="League Move Org").default_league_id,
            league.pk,
        )
        self.assertEqual(
            Tournament.objects.get(name="League Move Tournament").league_id, league.pk
        )
        self.assertEqual(
            Event.objects.get(name="League Move Event").tournament_league_id, league.pk
        )
        self.assertEqual(
            list(LeagueUser.objects.values_list("league_id", flat=True)), [league.pk]
        )
        self.assertEqual(
            list(league.games.values_list("league_id", flat=True)), [league.pk]
        )

    def test_reverse_then_forward_keeps_schema_and_relabels(self) -> None:
        ids = {
            model: ContentType.objects.get_or_create(app_label=LEAGUE, model=model)[
                0
            ].pk
            for model in LEAGUE_MODELS
        }
        member_ct = ContentType.objects.get_or_create(
            app_label=LEAGUE, model="leagueuser"
        )[0].pk
        perm, user, group = self._grant(ids["league"], "league", "move")
        member_perm, member_user, member_group = self._grant(
            member_ct, "leagueuser", "member"
        )
        league = self._seed(user)
        counts = _row_counts()
        self.assertEqual(
            counts,
            {
                "app_league": 1,
                "app_league_admins": 1,
                "app_league_staff": 1,
                "app_leaguerating": 1,
                "app_leaguematch": 1,
                "app_leaguematchparticipant": 1,
                "app_leaguelog": 1,
                "league_leagueuser": 1,
            },
        )
        schema_head = _schema_rows()
        self.assertEqual(
            {row[2] for row in schema_head}, set(MOVED_TABLES + REFERRING_TABLES)
        )
        self.assertTrue(any(row[0] == "index" for row in schema_head))
        self._migrate(AFTER_MOVE)
        schema_before = _schema_rows()

        self._migrate(BEFORE_MOVE)

        self.assertEqual(self._labels(ids), {m: (APP, m) for m in LEAGUE_MODELS})
        self.assertEqual(self._labels({"m": member_ct}), {"m": (LEAGUE, "leagueuser")})
        self._assert_grant(perm, user, group, ids["league"])
        self._assert_grant(member_perm, member_user, member_group, member_ct)
        self.assertEqual(_row_counts(), counts)
        self.assertEqual(_schema_rows(), schema_before)

        self._forward()

        self.assertEqual(self._labels(ids), {m: (LEAGUE, m) for m in LEAGUE_MODELS})
        self.assertEqual(self._labels({"m": member_ct}), {"m": (LEAGUE, "leagueuser")})
        self._assert_grant(perm, user, group, ids["league"])
        self._assert_grant(member_perm, member_user, member_group, member_ct)
        self.assertEqual(_row_counts(), counts)
        self._assert_links(league)
        self._migrate(AFTER_MOVE)
        self.assertEqual(_schema_rows(), schema_before)

    def test_duplicate_contenttypes_survive_both_directions(self) -> None:
        original, _ = ContentType.objects.get_or_create(
            app_label=LEAGUE, model="league"
        )
        perm, user, group = self._grant(original.pk, "league", "dup")

        self._migrate(BEFORE_MOVE)
        self.assertEqual(self._labels({"o": original.pk}), {"o": (APP, "league")})
        duplicate = ContentType.objects.create(app_label=LEAGUE, model="league")
        expected = {"o": (APP, "league"), "d": (LEAGUE, "league")}
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
            skipped, [("league", "app->league"), ("league", "league->app")]
        )

    def test_retargets_precede_app_0112(self) -> None:
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
        indexed: tuple[type[models.Model], ...] = (League, LeagueLog, Game)
        with connection.cursor() as cursor:
            for model in indexed:
                constraints = connection.introspection.get_constraints(
                    cursor, model._meta.db_table
                )
                self.assertTrue(model._meta.indexes, model.__name__)
                for index in model._meta.indexes:
                    self.assertIn(index.name, constraints, model.__name__)
