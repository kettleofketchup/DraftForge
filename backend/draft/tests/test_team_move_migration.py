from django.contrib.admin.models import ADDITION, LogEntry
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader
from django.test import TransactionTestCase
from django.utils import timezone

from app.models import CustomUser, Tournament
from discordbot.models import DraftActivityChannel
from draft.models import Draft, DraftEvent, DraftOptions, DraftRound

TEAM_MODELS = ("draft", "draftround", "draftevent", "draftoptions")
TEAM_TABLES = ("app_draft", "app_draftround", "app_draftevent", "app_draftoptions")
DISCORDBOT_TABLES = (
    "discordbot_draftactivitychannel",
    "discordbot_draftactivityinstance",
)
BEFORE_MOVE = [
    ("app", "0108_move_hero_draft_models_to_draft"),
    ("discordbot", "0013_retarget_draft_activity_herodraft"),
    ("draft", "0001_move_hero_draft_models"),
]
MOVE_MIGRATION = ("app", "0109_move_team_draft_models_to_draft")
EVENTS_BACKFILL = ("events", "0024_backfill_event_draft_options")
APP = "app"
DRAFT = "draft"


def _table_sql() -> dict[str, str]:
    tables = TEAM_TABLES + DISCORDBOT_TABLES
    with connection.cursor() as cursor:
        placeholders = ",".join("%s" for _ in tables)
        cursor.execute(
            f"SELECT name, sql FROM sqlite_master WHERE name IN ({placeholders})",
            list(tables),
        )
        return dict(cursor.fetchall())


def _row_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    with connection.cursor() as cursor:
        for table in TEAM_TABLES + DISCORDBOT_TABLES:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            counts[table] = cursor.fetchone()[0]
    return counts


class TeamMoveMigrationTests(TransactionTestCase):
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

    def _seed_draft(self, actor: CustomUser) -> Draft:
        tournament = Tournament.objects.create(
            name="Team Move Migration Cup", date_played=timezone.now()
        )
        draft = Draft.objects.create(tournament=tournament)
        DraftRound.objects.create(draft=draft, captain=actor, pick_number=1)
        DraftEvent.objects.create(draft=draft, event_type="draft_started", actor=actor)
        DraftOptions.objects.get_or_create(tournament=tournament)
        DraftActivityChannel.objects.create(
            guild_id="1", channel_id="team-move-1", team_draft=draft
        )
        return draft

    def test_reverse_then_forward_relabels_and_keeps_data(self) -> None:
        ids = {
            model: ContentType.objects.get_or_create(app_label=DRAFT, model=model)[0].pk
            for model in TEAM_MODELS
        }
        perm, _ = Permission.objects.get_or_create(
            codename="change_draft",
            content_type_id=ids["draft"],
            defaults={"name": "Can change draft"},
        )
        user = CustomUser.objects.create_user(username="team_perm_user")
        group = Group.objects.create(name="team_perm_group")
        user.user_permissions.add(perm)
        group.permissions.add(perm)
        draft = self._seed_draft(user)
        log_entry = LogEntry.objects.create(
            user=user,
            content_type_id=ids["draft"],
            object_id=str(draft.pk),
            object_repr=str(draft),
            action_flag=ADDITION,
        )
        counts = _row_counts()
        self.assertEqual(
            counts,
            {
                "app_draft": 1,
                "app_draftround": 1,
                "app_draftevent": 1,
                "app_draftoptions": 1,
                "discordbot_draftactivitychannel": 1,
                "discordbot_draftactivityinstance": 0,
            },
        )
        sql_before = _table_sql()
        self.assertEqual(set(sql_before), set(TEAM_TABLES + DISCORDBOT_TABLES))

        self._migrate(BEFORE_MOVE)

        self.assertEqual(
            self._labels(ids), {model: (APP, model) for model in TEAM_MODELS}
        )
        perm.refresh_from_db()
        self.assertEqual(perm.content_type_id, ids["draft"])
        self.assertTrue(user.user_permissions.filter(pk=perm.pk).exists())
        self.assertTrue(group.permissions.filter(pk=perm.pk).exists())
        log_entry.refresh_from_db()
        self.assertEqual(log_entry.content_type_id, ids["draft"])
        self.assertEqual(_row_counts(), counts)
        self.assertEqual(_table_sql(), sql_before)

        self._forward()

        self.assertEqual(
            self._labels(ids), {model: (DRAFT, model) for model in TEAM_MODELS}
        )
        perm.refresh_from_db()
        self.assertEqual(perm.content_type_id, ids["draft"])
        self.assertTrue(user.user_permissions.filter(pk=perm.pk).exists())
        self.assertTrue(group.permissions.filter(pk=perm.pk).exists())
        log_entry.refresh_from_db()
        self.assertEqual(log_entry.content_type_id, ids["draft"])
        self.assertEqual(_row_counts(), counts)
        self.assertEqual(_table_sql(), sql_before)
        self.assertEqual(
            DraftActivityChannel.objects.get(channel_id="team-move-1").team_draft_id,
            draft.pk,
        )

    def test_duplicate_contenttypes_survive_both_directions(self) -> None:
        draft_ct, _ = ContentType.objects.get_or_create(
            app_label=DRAFT, model="draftoptions"
        )
        app_ct, _ = ContentType.objects.get_or_create(
            app_label=APP, model="draftoptions"
        )
        expected = {"d": (DRAFT, "draftoptions"), "a": (APP, "draftoptions")}

        self._migrate(BEFORE_MOVE)
        self.assertEqual(self._labels({"d": draft_ct.pk, "a": app_ct.pk}), expected)

        self._forward()
        self.assertEqual(self._labels({"d": draft_ct.pk, "a": app_ct.pk}), expected)

    def test_events_0024_precedes_app_0109(self) -> None:
        graph = MigrationLoader(connection).graph
        self.assertIn(EVENTS_BACKFILL, graph.forwards_plan(MOVE_MIGRATION))
