from django.test import TestCase

from app.models import CustomUser, PositionsModel

from user.serializers import UserProfileLayeredSerializer


class GameUserSerializerTests(TestCase):
    def test_layered_gameuser_has_dota_and_deadlock(self):
        user = CustomUser.objects.create(username="ser")
        user.dota_user_profile.positions = PositionsModel.objects.create(carry=4)
        user.dota_user_profile.save()
        dl = user.base_profile.deadlock_user_profile
        dl.rank = "Phantom"
        dl.save()

        data = UserProfileLayeredSerializer(user).data
        assert data["gameUser"]["dota"]["positions"]["carry"] == 4
        assert data["gameUser"]["dota"]["has_active_dota_mmr"] is False
        assert data["gameUser"]["deadlock"]["rank"] == "Phantom"
