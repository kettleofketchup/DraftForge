from datetime import date

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from app.models import CustomUser
from tournament.models import Team, Tournament

TOKEN = "test-internal-token"
HEADERS = {"HTTP_X_INTERNAL_TOKEN": TOKEN}


@override_settings(INTERNAL_SERVICE_TOKEN=TOKEN)
class TournamentParticipantsEndpointTest(TestCase):
    """get_tournament_participants returns the full Tournament.users pool."""

    def setUp(self):
        self.client = APIClient()
        self.client.credentials(**HEADERS)

        self.tournament = Tournament.objects.create(
            name="Participants Tournament", date_played=date.today()
        )
        # Captain: in the pool and seeded onto a team roster.
        self.captain = CustomUser.objects.create_user(
            username="cap", password="pw", discordId="1001"
        )
        # Undrafted participant: in the pool, on no team yet.
        self.participant = CustomUser.objects.create_user(
            username="pleb", password="pw", discordId="1002"
        )
        # Participant without a Discord link: must be excluded.
        self.no_discord = CustomUser.objects.create_user(
            username="nodiscord", password="pw"
        )
        self.tournament.users.add(self.captain, self.participant, self.no_discord)

        team = Team.objects.create(
            name="Team A", captain=self.captain, tournament=self.tournament
        )
        team.members.add(self.captain)

    def _get(self):
        return self.client.get(
            f"/api/internal/tournaments/{self.tournament.pk}/participants/"
        )

    def test_returns_full_pool_including_undrafted(self):
        resp = self._get()
        self.assertEqual(resp.status_code, 200)
        discord_ids = sorted(p["discord_id"] for p in resp.json())
        # Captain (drafted) AND undrafted participant both included.
        self.assertEqual(discord_ids, ["1001", "1002"])

    def test_excludes_users_without_discord_id(self):
        resp = self._get()
        returned_pks = {p["user_pk"] for p in resp.json()}
        self.assertNotIn(self.no_discord.pk, returned_pks)

    def test_no_duplicate_for_captain_in_pool_and_roster(self):
        resp = self._get()
        captain_rows = [p for p in resp.json() if p["discord_id"] == "1001"]
        self.assertEqual(len(captain_rows), 1)
