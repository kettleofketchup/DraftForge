"""reconcile-dota-lobbies must be in both beat schedules.

Production beat runs config.celery_light, whose schedule is a hand-kept copy
of config.celery's. The files are parsed rather than imported: importing
celery_light sets up Django with the worker settings.
"""

import ast
from pathlib import Path

from django.test import SimpleTestCase

CONFIG = Path(__file__).resolve().parents[2] / "config"


def beat_schedule(filename: str) -> dict[str, dict]:
    tree = ast.parse((CONFIG / filename).read_text())
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "_beat_schedule"
        ):
            schedule = {}
            for key, value in zip(node.value.keys, node.value.values):
                entry = {}
                for k, v in zip(value.keys, value.values):
                    if isinstance(v, ast.Constant):
                        entry[k.value] = v.value
                schedule[key.value] = entry
            return schedule
    raise AssertionError(f"no _beat_schedule in {filename}")


class BeatScheduleTests(SimpleTestCase):
    def test_reconcile_in_both_schedules(self):
        for filename in ("celery.py", "celery_light.py"):
            with self.subTest(filename=filename):
                entry = beat_schedule(filename)["reconcile-dota-lobbies"]
                self.assertEqual(entry["task"], "lobby.tasks.reconcile_dota_lobbies")
                self.assertEqual(entry["schedule"], 60.0)

    def test_task_is_registered(self):
        from lobby.tasks import reconcile_dota_lobbies

        self.assertEqual(
            reconcile_dota_lobbies.name, "lobby.tasks.reconcile_dota_lobbies"
        )
