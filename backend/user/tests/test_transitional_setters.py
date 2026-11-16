from django.test import TestCase

from app.models import CustomUser


class CustomUserTransitionalSettersTests(TestCase):
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
        """`CustomUser.objects.create(avatar=...)` exercises the @property setter.

        Django's `Model.__init__` calls `setattr` for unknown kwargs, which
        dispatches to the `avatar` property setter. With no pk yet it buffers
        `_pending_avatar`; `save()` then auto-creates the BaseUserProfile and
        flushes the buffer.
        """
        user = CustomUser.objects.create(
            username="jake",
            avatar="https://example.com/jake.png",
        )
        user.base_profile.refresh_from_db()
        assert user.base_profile.avatar == "https://example.com/jake.png"
        # Buffer cleared after successful save.
        assert not hasattr(user, "_pending_avatar")
