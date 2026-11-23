"""Drift tests for the tournament schemas celery workers read.

Run: just test::run 'python manage.py test tournament.tests.test_schema_drift -v 2'
"""

from django.test import TestCase
from django.utils import timezone
from pydantic import ValidationError

from app.models import Tournament
from tournament.schemas import (
    GameWithoutHeroDraftSchema,
    TournamentParticipantSchema,
    TournamentTaskSchema,
)


class TournamentTaskSchemaDriftTest(TestCase):
    """Verify Tournament model output validates against TournamentTaskSchema."""

    def test_tournament_validates(self):
        t = Tournament.objects.create(
            name="Test", state="future", date_played=timezone.now()
        )
        data = {
            "id": t.pk,
            "name": t.name,
            "state": t.state,
            "auto_create_hero_drafts": t.auto_create_hero_drafts,
            "discord_send_draft_link": t.discord_send_draft_link,
            "discord_send_herodraft_link": t.discord_send_herodraft_link,
            "tournament_type": t.tournament_type,
            "draft_type": t.draft_type,
        }
        parsed = TournamentTaskSchema.model_validate(data)
        self.assertEqual(parsed.pk, t.pk)
        self.assertFalse(parsed.auto_create_hero_drafts)

    def test_extra_fields_ignored(self):
        data = {
            "id": 1,
            "name": "T",
            "state": "future",
            "some_new_field": "ignored",
        }
        parsed = TournamentTaskSchema.model_validate(data)
        self.assertEqual(parsed.id, 1)

    def test_missing_required_field_raises(self):
        with self.assertRaises(ValidationError):
            TournamentTaskSchema(name="T")  # missing id and state


class GameWithoutHeroDraftSchemaDriftTest(TestCase):
    def test_game_without_herodraft_validates(self):
        data = {
            "id": 1,
            "radiant_team_id": 10,
            "radiant_team_name": "Team A",
            "dire_team_id": 20,
            "dire_team_name": "Team B",
            "round": 1,
            "has_captains": True,
        }
        parsed = GameWithoutHeroDraftSchema.model_validate(data)
        self.assertEqual(parsed.id, 1)
        self.assertTrue(parsed.has_captains)


class TournamentParticipantSchemaDriftTest(TestCase):
    def test_participant_validates(self):
        data = {"user_pk": 1, "discord_id": "123456789", "username": "player1"}
        parsed = TournamentParticipantSchema.model_validate(data)
        self.assertEqual(parsed.discord_id, "123456789")

    def test_extra_fields_ignored(self):
        data = {
            "user_pk": 1,
            "discord_id": "123",
            "username": "p",
            "extra_field": "ignored",
        }
        parsed = TournamentParticipantSchema.model_validate(data)
        self.assertEqual(parsed.user_pk, 1)
