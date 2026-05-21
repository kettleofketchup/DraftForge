from django.test import TestCase

from app.models import CustomUser


class CustomUserTransitionalSettersTests(TestCase):
    def test_nickname_getter_reads_from_base_profile(self):
        user = CustomUser.objects.create(username="gina")
        user.base_profile.nickname = "Gina Display"
        user.base_profile.save()
        # Read via the property
        assert user.nickname == "Gina Display"

    def test_nickname_setter_writes_to_base_profile(self):
        user = CustomUser.objects.create(username="hans")
        user.nickname = "Hans New"  # transitional setter persists immediately
        user.base_profile.refresh_from_db()
        assert user.base_profile.nickname == "Hans New"

    def test_avatar_round_trip(self):
        user = CustomUser.objects.create(username="ida")
        user.avatar = "https://example.com/ida.png"
        user.base_profile.refresh_from_db()
        assert user.base_profile.avatar == "https://example.com/ida.png"
        assert user.avatar == "https://example.com/ida.png"

    def test_fields_removed_from_meta(self):
        # The actual model field is gone; only the property remains.
        field_names = {f.name for f in CustomUser._meta.get_fields()}
        assert "nickname" not in field_names
        assert "avatar" not in field_names

    def test_populate_style_create_keeps_working(self):
        # Mirror the populate-helper call shape: CustomUser(nickname=..., avatar=..., ...)
        user = CustomUser.objects.create(
            username="jake",
            nickname="Jake Initial",
            avatar="https://example.com/jake.png",
        )
        # base_profile is auto-created; transitional setter fired during __init__/save
        user.base_profile.refresh_from_db()
        assert user.base_profile.nickname == "Jake Initial"
        assert user.base_profile.avatar == "https://example.com/jake.png"
