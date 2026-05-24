"""Tests for Discord phantom-account reclamation.

Covers the root cause of `IntegrityError: UNIQUE constraint failed:
app_customuser.discordId` on /complete/discord/ — a Discord button signup
creates an account carrying `discordId`, then a login created a duplicate and
collided. See app/discord_accounts.py and app/pipelines.py.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone as tz
from social_django.models import UserSocialAuth

from app.discord_accounts import find_split_discord_accounts, merge_discord_accounts
from app.models import CustomUser, Organization
from app.pipelines import associate_by_discord_id, save_discord
from events.constants import EventState, SignupStatus
from events.models import Event, EventSignup

DISCORD_ID = "555000111222333444"


def _social(user, uid=DISCORD_ID, username="loginname", avatar="abc123"):
    return UserSocialAuth.objects.create(
        user=user,
        provider="discord",
        uid=uid,
        extra_data={"id": uid, "avatar": avatar, "username": username},
    )


class AssociateByDiscordIdTest(TestCase):
    def test_reclaims_existing_account_by_uid(self):
        """Login with a uid matching a phantom's discordId adopts that account."""
        phantom = CustomUser.objects.create(username="ph", discordId=DISCORD_ID)
        result = associate_by_discord_id(
            uid=DISCORD_ID, user=None, response={"id": DISCORD_ID}
        )
        self.assertEqual(result, {"user": phantom})

    def test_reads_uid_from_response_when_kwarg_absent(self):
        phantom = CustomUser.objects.create(username="ph", discordId=DISCORD_ID)
        result = associate_by_discord_id(user=None, response={"id": DISCORD_ID})
        self.assertEqual(result, {"user": phantom})

    def test_returns_none_when_already_authenticated(self):
        CustomUser.objects.create(username="ph", discordId=DISCORD_ID)
        already = CustomUser.objects.create(username="me")
        self.assertIsNone(
            associate_by_discord_id(uid=DISCORD_ID, user=already)
        )

    def test_returns_none_when_no_match(self):
        self.assertIsNone(associate_by_discord_id(uid="does-not-exist", user=None))

    def test_returns_none_when_no_uid(self):
        self.assertIsNone(associate_by_discord_id(user=None, response={}))


class MergeDiscordAccountsTest(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create(username="org_admin")
        self.org = Organization.objects.create(name="Reclaim Org", owner=self.admin)
        self.event = Event.objects.create(
            organization=self.org,
            name="Reclaim Event",
            scheduled_at=tz.now() + timedelta(days=3),
            state=EventState.SIGNUPS_OPEN,
            created_by=self.admin,
        )

    def test_merge_moves_social_auth_and_keeps_signup(self):
        # Phantom holds the discordId and the real signup, but no social link.
        keep = CustomUser.objects.create(username="ph", discordId=DISCORD_ID)
        EventSignup.objects.create(
            event=self.event, user=keep, status=SignupStatus.RSVP
        )
        # Duplicate login row holds the social-auth link, no discordId.
        drop = CustomUser.objects.create(username="loginrow")
        _social(drop)

        merged = merge_discord_accounts(keep=keep, drop=drop)

        self.assertEqual(merged.pk, keep.pk)
        self.assertFalse(CustomUser.objects.filter(pk=drop.pk).exists())
        # Signup preserved on the kept account.
        self.assertTrue(
            EventSignup.objects.filter(event=self.event, user=keep).exists()
        )
        # Social-auth link now points at the kept account.
        self.assertTrue(
            UserSocialAuth.objects.filter(
                user=keep, provider="discord", uid=DISCORD_ID
            ).exists()
        )

    def test_merge_carries_over_missing_avatar(self):
        keep = CustomUser.objects.create(username="ph", discordId=DISCORD_ID)
        drop = CustomUser.objects.create(username="loginrow", avatar="newavatar")
        _social(drop, avatar="newavatar")

        merge_discord_accounts(keep=keep, drop=drop)
        keep.refresh_from_db()
        self.assertEqual(keep.avatar, "newavatar")

    def test_merge_handles_reverse_one_to_one(self):
        """Reverse O2O relations (e.g. Joke) move across without crashing."""
        from app.models import Joke

        keep = CustomUser.objects.create(username="ph", discordId=DISCORD_ID)
        drop = CustomUser.objects.create(username="loginrow")
        _social(drop)
        Joke.objects.create(user=drop, tangoes_purchased=7)

        merge_discord_accounts(keep=keep, drop=drop)

        self.assertFalse(CustomUser.objects.filter(pk=drop.pk).exists())
        keep.refresh_from_db()
        self.assertEqual(keep.joke.tangoes_purchased, 7)

    def test_merge_reverse_one_to_one_conflict_keeps_existing(self):
        """When both rows have the O2O, keep's wins and drop's is discarded."""
        from app.models import Joke

        keep = CustomUser.objects.create(username="ph", discordId=DISCORD_ID)
        Joke.objects.create(user=keep, tangoes_purchased=3)
        drop = CustomUser.objects.create(username="loginrow")
        Joke.objects.create(user=drop, tangoes_purchased=9)
        _social(drop)

        merge_discord_accounts(keep=keep, drop=drop)

        keep.refresh_from_db()
        self.assertEqual(keep.joke.tangoes_purchased, 3)
        self.assertEqual(Joke.objects.count(), 1)

    def test_find_split_accounts(self):
        keep = CustomUser.objects.create(username="ph", discordId=DISCORD_ID)
        drop = CustomUser.objects.create(username="loginrow")
        _social(drop)

        pairs = find_split_discord_accounts()
        self.assertEqual(pairs, [(keep, drop)])

    def test_find_split_ignores_consistent_account(self):
        """A normal account owning both discordId and its social link is not split."""
        user = CustomUser.objects.create(username="normal", discordId=DISCORD_ID)
        _social(user)
        self.assertEqual(find_split_discord_accounts(), [])


class GetOrgUserPhantomGuardTest(TestCase):
    """Guards on the Discord-button phantom-creation path (_get_org_user)."""

    def setUp(self):
        self.admin = CustomUser.objects.create(username="guard_admin")
        self.org = Organization.objects.create(name="Guard Org", owner=self.admin)
        self.event = Event.objects.create(
            organization=self.org,
            name="Guard Event",
            scheduled_at=tz.now() + timedelta(days=3),
            state=EventState.SIGNUPS_OPEN,
            created_by=self.admin,
        )

    def test_phantom_is_immediately_loginable(self):
        """A button-created phantom is a normal account a Discord login reclaims."""
        from events.discord.handlers import _get_org_user

        _, user = _get_org_user(self.event, DISCORD_ID, discord_username="ghost")
        self.assertEqual(user.discordId, DISCORD_ID)
        self.assertTrue(user.is_active)
        # A Discord OAuth login adopts this exact row — no restriction/claim step.
        self.assertEqual(
            associate_by_discord_id(uid=DISCORD_ID, user=None), {"user": user}
        )

    def test_repeat_click_reuses_same_account(self):
        """Clicking again resolves the same row — never a duplicate discordId."""
        from events.discord.handlers import _get_org_user

        _, first = _get_org_user(self.event, DISCORD_ID, discord_username="ghost")
        _, second = _get_org_user(self.event, DISCORD_ID, discord_username="ghost")
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(CustomUser.objects.filter(discordId=DISCORD_ID).count(), 1)

    def test_existing_real_account_is_reused_not_duplicated(self):
        """A real (login) account with this discordId is used, not shadowed."""
        from events.discord.handlers import _get_org_user

        real = CustomUser.objects.create(username="real", discordId=DISCORD_ID)
        real.set_password("hunter2")
        real.save()
        _, user = _get_org_user(self.event, DISCORD_ID, discord_username="ghost")
        self.assertEqual(user.pk, real.pk)
        self.assertTrue(user.has_usable_password())

    def test_unclaimed_account_with_same_username_is_claimed(self):
        """Discord usernames are unique: an unclaimed row with that handle is
        the same person, so it's claimed (discordId set) — not duplicated/mangled."""
        from events.discord.handlers import _get_org_user

        existing = CustomUser.objects.create(username="alice")  # no discordId yet
        _, user = _get_org_user(self.event, DISCORD_ID, discord_username="alice")
        self.assertEqual(user.pk, existing.pk)
        user.refresh_from_db()
        self.assertEqual(user.discordId, DISCORD_ID)
        # No duplicate / no "_1" mangled account.
        self.assertEqual(CustomUser.objects.filter(username="alice").count(), 1)
        self.assertFalse(CustomUser.objects.filter(username="alice_1").exists())

    def test_username_owned_by_other_discord_id_is_not_hijacked(self):
        """A handle already linked to a *different* Discord ID is left alone."""
        from events.discord.handlers import _get_org_user

        other = CustomUser.objects.create(username="alice", discordId="999888777")
        _, user = _get_org_user(self.event, DISCORD_ID, discord_username="alice")
        self.assertNotEqual(user.pk, other.pk)
        other.refresh_from_db()
        self.assertEqual(other.discordId, "999888777")
        self.assertEqual(user.discordId, DISCORD_ID)


class SaveDiscordCollisionTest(TestCase):
    def test_save_discord_merges_instead_of_integrityerror(self):
        """The exact production crash: login row collides with a phantom's discordId."""
        phantom = CustomUser.objects.create(username="ph", discordId=DISCORD_ID)
        login_row = CustomUser.objects.create(username="loginrow")
        _social(login_row, username="realname", avatar="av")

        # Must not raise IntegrityError.
        result = save_discord(strategy=None, details={}, user=login_row)

        keep = result["user"]
        self.assertEqual(keep.pk, phantom.pk)
        # Exactly one account owns the discordId now.
        self.assertEqual(
            CustomUser.objects.filter(discordId=DISCORD_ID).count(), 1
        )
        self.assertFalse(CustomUser.objects.filter(pk=login_row.pk).exists())
        # Kept account is login-capable (has the social link) and updated.
        self.assertTrue(
            UserSocialAuth.objects.filter(user=keep, uid=DISCORD_ID).exists()
        )
        self.assertEqual(keep.username, "realname")

    def test_save_discord_merges_username_holder(self):
        """Login row's handle is still held by an unclaimed row -> merge, no crash."""
        # Login row carries the social link; a separate unclaimed row holds the
        # handle the OAuth login is about to write.
        login_row = CustomUser.objects.create(username="tmp_login")
        _social(login_row, username="realname", avatar="av")
        stale = CustomUser.objects.create(username="realname")  # no discordId

        result = save_discord(strategy=None, details={}, user=login_row)

        keep = result["user"]
        self.assertEqual(keep.pk, login_row.pk)
        self.assertFalse(CustomUser.objects.filter(pk=stale.pk).exists())
        self.assertEqual(CustomUser.objects.filter(username="realname").count(), 1)
        self.assertEqual(keep.username, "realname")
        self.assertEqual(keep.discordId, DISCORD_ID)

    def test_save_discord_normal_path_unchanged(self):
        """No collision: save_discord writes the discord fields and returns the user."""
        user = CustomUser.objects.create(username="fresh")
        _social(user, username="realname", avatar="av")

        result = save_discord(strategy=None, details={}, user=user)

        self.assertEqual(result["user"].pk, user.pk)
        user.refresh_from_db()
        self.assertEqual(user.discordId, DISCORD_ID)
        self.assertEqual(user.username, "realname")
        self.assertEqual(user.avatar, "av")
