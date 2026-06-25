from unittest.mock import patch

from django.test import TestCase

from app.models import CustomUser, PositionsModel


class PositionsInvalidationTests(TestCase):
    def test_save_walks_dotauserprofile_set_not_customuser_set(self):
        user = CustomUser.objects.create(username="inv")
        pos = user.base_profile.dota_user_profile.positions
        assert pos is not None
        # save() must invalidate the owning dota profile + bubbled parents,
        # NOT raise AttributeError on the now-empty customuser_set.
        with patch("app.cache_utils.invalidate_after_commit") as mock_inv:
            pos.carry = 5
            pos.save()
            assert mock_inv.called
            invalidated = mock_inv.call_args.args
            # dota profile, base profile, and user all targeted
            assert user.base_profile.dota_user_profile in invalidated
