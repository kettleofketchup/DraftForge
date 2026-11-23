import os
import subprocess
import sys
from datetime import date
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase

from discordbot.activity_targets import draft_site_url, draft_tournament_id
from draft.models import Draft, HeroDraft
from tournament.models import Game, Tournament

BACKEND_DIR = Path(__file__).resolve().parents[2]


class ActivityTargetsTests(TestCase):
    def setUp(self) -> None:
        self.tournament = Tournament.objects.create(
            name="Targets", date_played=date.today()
        )
        self.hero = HeroDraft.objects.create(
            game=Game.objects.create(tournament=self.tournament)
        )
        self.team_draft = Draft.objects.create(tournament=self.tournament)

    def test_draft_tournament_id(self) -> None:
        self.assertEqual(draft_tournament_id(self.hero), self.tournament.pk)
        self.assertEqual(draft_tournament_id(self.team_draft), self.tournament.pk)
        loose = HeroDraft.objects.create(game=Game.objects.create(tournament=None))
        self.assertIsNone(draft_tournament_id(loose))
        self.assertIsNone(draft_tournament_id(Draft(tournament=None)))

    def test_draft_site_url(self) -> None:
        self.assertEqual(
            draft_site_url("hero", self.hero),
            f"{settings.SITE_URL}/herodraft/{self.hero.pk}",
        )
        self.assertEqual(
            draft_site_url("team", self.team_draft),
            f"{settings.SITE_URL}/tournament/{self.tournament.pk}/teams/draft",
        )


class ActivityImportTests(SimpleTestCase):
    def test_activity_modules_import_without_cycles(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import django; django.setup(); "
                "import discordbot.activity_targets, discordbot.urls, "
                "tournament.routing, draft.routing, discordbot.activity_launch",
            ],
            cwd=BACKEND_DIR,
            env=os.environ,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
