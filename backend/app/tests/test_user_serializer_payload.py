from django.test import TestCase
from django.utils import timezone

from app.models import CustomUser, PositionsModel, Team, Tournament
from app.serializers import UserSerializer


class UserSerializerPayloadTest(TestCase):
    def test_user_serializer_omits_teams(self) -> None:
        user = CustomUser.objects.create(
            username="usp_member", positions=PositionsModel.objects.create()
        )
        tournament = Tournament.objects.create(
            name="Payload Cup",
            tournament_type="single_elimination",
            date_played=timezone.now(),
        )
        tournament.users.add(user)
        team = Team.objects.create(tournament=tournament, name="Payload Team")
        team.members.add(user)

        data = UserSerializer(user).data

        self.assertNotIn("teams", data)
