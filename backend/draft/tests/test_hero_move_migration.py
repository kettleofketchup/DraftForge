from django.contrib.admin.models import ADDITION, LogEntry
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone

from app.models import CustomUser
from draft.models import DraftTeam, HeroDraft, HeroDraftEvent, HeroDraftRound
from tournament.models import Game, Team, Tournament

HERO_MODELS = ("herodraft", "draftteam", "herodraftround", "herodraftevent")
HERO_TABLES = (
    "app_herodraft",
    "app_draftteam",
    "app_herodraftround",
    "app_herodraftevent",
)
BEFORE_MOVE = [
    ("app", "0107_teamlog"),
    ("discordbot", "0012_draftactivitychannel_draftactivityinstance"),
    ("draft", None),
]
APP = "app"
DRAFT = "draft"


def _table_sql() -> dict[str, str]:
    with connection.cursor() as cursor:
        placeholders = ",".join("%s" for _ in HERO_TABLES)
        cursor.execute(
            f"SELECT name, sql FROM sqlite_master WHERE name IN ({placeholders})",
            list(HERO_TABLES),
        )
        return dict(cursor.fetchall())


class HeroMoveMigrationTests(TransactionTestCase):
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
            model: tuple(
                ContentType.objects.filter(pk=pk).values_list("app_label", "model")[0]
            )
            for model, pk in ids.items()
        }

    def _seed_draft(self) -> HeroDraft:
        tournament = Tournament.objects.create(
            name="Move Migration Cup", date_played=timezone.now()
        )
        radiant = Team.objects.create(name="Radiant", tournament=tournament)
        dire = Team.objects.create(name="Dire", tournament=tournament)
        game = Game.objects.create(
            tournament=tournament, radiant_team=radiant, dire_team=dire
        )
        draft = HeroDraft.objects.create(game=game)
        team = DraftTeam.objects.create(draft=draft, tournament_team=radiant)
        HeroDraftRound.objects.create(
            draft=draft, draft_team=team, round_number=1, action_type="ban"
        )
        HeroDraftEvent.objects.create(draft=draft, event_type="captain_ready")
        return draft

    def test_reverse_then_forward_relabels_and_keeps_data(self) -> None:
        ids = {
            model: ContentType.objects.get_or_create(app_label=DRAFT, model=model)[0].pk
            for model in HERO_MODELS
        }
        perm, _ = Permission.objects.get_or_create(
            codename="change_herodraft",
            content_type_id=ids["herodraft"],
            defaults={"name": "Can change hero draft"},
        )
        user = CustomUser.objects.create_user(username="hero_perm_user")
        group = Group.objects.create(name="hero_perm_group")
        user.user_permissions.add(perm)
        group.permissions.add(perm)
        draft = self._seed_draft()
        log_entry = LogEntry.objects.create(
            user=user,
            content_type_id=ids["herodraft"],
            object_id=str(draft.pk),
            object_repr=str(draft),
            action_flag=ADDITION,
        )
        counts = {m: m.objects.count() for m in (HeroDraft, DraftTeam)}
        sql_before = _table_sql()
        self.assertEqual(set(sql_before), set(HERO_TABLES))

        self._migrate(BEFORE_MOVE)

        self.assertEqual(
            self._labels(ids), {model: (APP, model) for model in HERO_MODELS}
        )
        perm.refresh_from_db()
        self.assertEqual(perm.content_type_id, ids["herodraft"])
        self.assertTrue(user.user_permissions.filter(pk=perm.pk).exists())
        self.assertTrue(group.permissions.filter(pk=perm.pk).exists())
        log_entry.refresh_from_db()
        self.assertEqual(log_entry.content_type_id, ids["herodraft"])
        self.assertEqual(_table_sql(), sql_before)
        with connection.cursor() as cursor:
            for table, expected in (
                ("app_herodraft", 1),
                ("app_draftteam", 1),
                ("app_herodraftround", 1),
                ("app_herodraftevent", 1),
            ):
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                self.assertEqual(cursor.fetchone()[0], expected, table)

        self._forward()

        self.assertEqual(
            self._labels(ids), {model: (DRAFT, model) for model in HERO_MODELS}
        )
        self.assertEqual({m: m.objects.count() for m in (HeroDraft, DraftTeam)}, counts)
        self.assertEqual(_table_sql(), sql_before)
        log_entry.refresh_from_db()
        self.assertEqual(log_entry.content_type_id, ids["herodraft"])

    def test_duplicate_contenttypes_survive_both_directions(self) -> None:
        draft_ct, _ = ContentType.objects.get_or_create(
            app_label=DRAFT, model="herodraft"
        )
        app_ct, _ = ContentType.objects.get_or_create(app_label=APP, model="herodraft")

        self._migrate(BEFORE_MOVE)
        self.assertEqual(
            self._labels({"d": draft_ct.pk, "a": app_ct.pk}),
            {"d": (DRAFT, "herodraft"), "a": (APP, "herodraft")},
        )

        self._forward()
        self.assertEqual(
            self._labels({"d": draft_ct.pk, "a": app_ct.pk}),
            {"d": (DRAFT, "herodraft"), "a": (APP, "herodraft")},
        )
