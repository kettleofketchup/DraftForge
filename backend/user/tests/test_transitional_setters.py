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
        """`CustomUser.objects.create(nickname=...)` exercises the @property setter.

        Surface-level instinct says `nickname`/`avatar` are no longer model
        fields, so kwargs passed to `objects.create()` would land in
        `instance.__dict__` and bypass the descriptor entirely — and the test
        would pass for the wrong reason (the kwarg-set value just happens to
        equal the assertion).

        That instinct is wrong. Django's `Model.__init__` iterates over
        unknown kwargs and calls `setattr(self, key, value)`. Python's
        descriptor protocol then dispatches to any data descriptor (including
        `@property` setters) defined on the class. Since `nickname` IS a data
        descriptor on `CustomUser` (defined via `@property` + `@nickname.setter`
        in app/models.py:151), `setattr` fires the setter — which buffers
        `_pending_nickname` because `self.pk` is still None at that point.
        Then `objects.create()` calls `save()`, which auto-creates the
        BaseUserProfile and flushes the buffer at app/models.py:332-352.

        This test thus exercises the buffer-flush path end-to-end via the
        populate-helper call shape. Do NOT refactor it under the impression
        the descriptor is bypassed. The `test_nickname_setter_writes_to_base_profile`
        test above covers the bp-is-not-None branch directly.
        """
        user = CustomUser.objects.create(
            username="jake",
            nickname="Jake Initial",
            avatar="https://example.com/jake.png",
        )
        user.base_profile.refresh_from_db()
        assert user.base_profile.nickname == "Jake Initial"
        assert user.base_profile.avatar == "https://example.com/jake.png"
        # Buffer cleared after successful save.
        assert not hasattr(user, "_pending_nickname")
        assert not hasattr(user, "_pending_avatar")
