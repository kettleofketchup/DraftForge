"""Tests for Discord phantom-account reclamation.

Covers the root cause of `IntegrityError: UNIQUE constraint failed:
app_customuser.discordId` on /complete/discord/ — a Discord button signup
creates an account carrying `discordId`, then a login created a duplicate and
collided. See user/discord_accounts.py and user/pipelines.py.
"""

from datetime import UTC, date, datetime, timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone as tz
from social_django.models import UserSocialAuth

from app.models import CustomUser
from common.game import GameType
from discordbot.models import DiscordEvent, DiscordEventDM, DMType
from events.constants import EventState, SignupAction, SignupStatus
from events.ledger import ActorRole, SignupMeans
from events.models import Event, EventSignup, SignupLedgerEntry
from joke.models import Joke
from league.models import League, LeagueUser
from org.contributions.kinds import ContributionKind
from org.models import (
    ContributionEntry,
    Organization,
    OrgUser,
    OrgUserGameMmr,
    PlayerDotaProfile,
)
from tournament.models import Team, Tournament
from user.discord_accounts import (
    _CARRYOVER_COLUMN_FIELDS,
    find_split_discord_accounts,
    merge_discord_accounts,
)
from user.models import BaseUserProfile, DeadlockUserProfile, DotaUserProfile
from user.pipelines import associate_by_discord_id, save_discord

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
        self.assertIsNone(associate_by_discord_id(uid=DISCORD_ID, user=already))

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
        keep = CustomUser.objects.create(username="ph", discordId=DISCORD_ID)
        Joke.objects.create(user=keep, tangoes_purchased=3)
        drop = CustomUser.objects.create(username="loginrow")
        Joke.objects.create(user=drop, tangoes_purchased=9)
        _social(drop)

        merge_discord_accounts(keep=keep, drop=drop)

        keep.refresh_from_db()
        self.assertEqual(keep.joke.tangoes_purchased, 3)
        self.assertEqual(Joke.objects.count(), 1)

    def test_merge_with_points_in_both_accounts_keeps_total(self) -> None:
        keep = CustomUser.objects.create(username="ph", discordId=DISCORD_ID)
        drop = CustomUser.objects.create(username="loginrow")
        _social(drop)
        for user, points in ((keep, 5), (drop, 3)):
            org_user = OrgUser.objects.create(user=user, organization=self.org)
            ContributionEntry.objects.create(
                org_user=org_user,
                organization=self.org,
                kind=ContributionKind.MANUAL,
                points=points,
                reason="help",
                occurred_at=tz.now(),
            )

        merge_discord_accounts(keep=keep, drop=drop)

        self.assertFalse(CustomUser.objects.filter(pk=drop.pk).exists())
        self.assertEqual(
            sorted(
                ContributionEntry.objects.nocache().values_list(
                    "org_user__user_id", "points"
                )
            ),
            [(keep.pk, 3), (keep.pk, 5)],
        )

    def test_merge_collision_keeps_dropped_guild_nickname(self) -> None:
        keep = CustomUser.objects.create(username="ph", discordId=DISCORD_ID)
        drop = CustomUser.objects.create(username="loginrow")
        _social(drop)
        keep_ou = OrgUser.objects.create(user=keep, organization=self.org)
        OrgUser.objects.create(
            user=drop, organization=self.org, guild_nickname="DragonClaw"
        )

        with mock.patch("user.discord_accounts.invalidate_after_commit") as spy:
            merge_discord_accounts(keep=keep, drop=drop)

        self.assertEqual(
            OrgUser.objects.nocache().get(pk=keep_ou.pk).guild_nickname, "DragonClaw"
        )
        self.assertTrue(
            any(
                isinstance(a, CustomUser) and a.pk == keep.pk
                for call in spy.call_args_list
                for a in call.args
            )
        )

    def test_merge_collision_keeps_existing_guild_nickname(self) -> None:
        keep = CustomUser.objects.create(username="ph", discordId=DISCORD_ID)
        drop = CustomUser.objects.create(username="loginrow")
        _social(drop)
        keep_ou = OrgUser.objects.create(
            user=keep, organization=self.org, guild_nickname="KeepNick"
        )
        OrgUser.objects.create(
            user=drop, organization=self.org, guild_nickname="DropNick"
        )

        merge_discord_accounts(keep=keep, drop=drop)

        self.assertEqual(
            OrgUser.objects.nocache().get(pk=keep_ou.pk).guild_nickname, "KeepNick"
        )

    def test_merge_keeps_per_game_org_mmrs(self) -> None:
        keep = CustomUser.objects.create(username="ph", discordId=DISCORD_ID)
        drop = CustomUser.objects.create(username="loginrow")
        _social(drop)
        keep_ou = OrgUser.objects.create(user=keep, organization=self.org)
        OrgUser.objects.filter(pk=keep_ou.pk).update(
            has_active_dota_mmr=False, dota_mmr_last_verified=None
        )
        drop_ou = OrgUser.objects.create(user=drop, organization=self.org)
        OrgUserGameMmr.objects.create(
            org_user=keep_ou, game_type=GameType.DOTA2, mmr=4000
        )
        OrgUserGameMmr.objects.create(
            org_user=drop_ou, game_type=GameType.DOTA2, mmr=25000
        )
        OrgUserGameMmr.objects.create(
            org_user=drop_ou, game_type=GameType.DEADLOCK, mmr=2500
        )

        merge_discord_accounts(keep=keep, drop=drop)

        self.assertEqual(
            dict(
                OrgUserGameMmr.objects.nocache()
                .filter(org_user_id=keep_ou.pk)
                .values_list("game_type", "mmr")
            ),
            {GameType.DOTA2: 25000, GameType.DEADLOCK: 2500},
        )
        kept = OrgUser.objects.nocache().get(pk=keep_ou.pk)
        self.assertFalse(kept.has_active_dota_mmr)
        self.assertIsNone(kept.dota_mmr_last_verified)

    def test_guild_nickname_not_carried_over_as_column(self) -> None:
        self.assertNotIn("guildNickname", _CARRYOVER_COLUMN_FIELDS)
        self.assertIn("discordNickname", _CARRYOVER_COLUMN_FIELDS)

    def test_merge_records_account_merged_as_system(self) -> None:
        keep = CustomUser.objects.create(username="ph", discordId=DISCORD_ID)
        drop = CustomUser.objects.create(username="loginrow")
        _social(drop)
        signup = EventSignup.objects.create(
            event=self.event, user=drop, status=SignupStatus.RSVP
        )
        drop_pk = drop.pk

        merge_discord_accounts(keep=keep, drop=drop)

        signup.refresh_from_db()
        self.assertEqual(signup.user_id, keep.pk)
        [entry] = SignupLedgerEntry.objects.filter(
            event=self.event, action=SignupAction.ACCOUNT_MERGED
        )
        self.assertEqual(entry.signup_id, signup.pk)
        self.assertEqual(entry.subject_user_id, keep.pk)
        self.assertIsNone(entry.actor_user_id)
        self.assertEqual(entry.actor_role, ActorRole.SYSTEM)
        self.assertEqual(entry.means, SignupMeans.SYSTEM)
        self.assertRegex(entry.correlation_id, r"^merge-[0-9a-f]{12}$")
        self.assertEqual(entry.before["extra"], {"from_user_id": drop_pk})

    def test_merge_aborts_when_ledger_write_fails(self) -> None:
        keep = CustomUser.objects.create(username="ph", discordId=DISCORD_ID)
        drop = CustomUser.objects.create(username="loginrow")
        _social(drop)
        signup = EventSignup.objects.create(event=self.event, user=drop)

        with (
            mock.patch(
                "events.merge.record_signup_change", side_effect=RuntimeError("boom")
            ),
            self.assertRaises(RuntimeError),
        ):
            merge_discord_accounts(keep=keep, drop=drop)

        self.assertTrue(CustomUser.objects.filter(pk=drop.pk).exists())
        self.assertTrue(CustomUser.objects.filter(pk=keep.pk).exists())
        self.assertEqual(
            EventSignup.objects.nocache().get(pk=signup.pk).user_id, drop.pk
        )

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


def _discarded(spy: mock.MagicMock) -> list[dict]:
    return [
        c.kwargs
        for c in spy.info.call_args_list
        if c.args and c.args[0] == "discord_merge_row_discarded"
    ]


class MergeDiscardedRowsTest(TestCase):
    """Rows the merge cannot move are logged, and the kept account inherits
    profile data it lacks instead of losing it with the dropped account."""

    def test_conflicting_row_is_logged(self) -> None:
        keep = CustomUser.objects.create(username="ph", discordId=DISCORD_ID)
        Joke.objects.create(user=keep, tangoes_purchased=3)
        drop = CustomUser.objects.create(username="loginrow")
        dropped_joke_pk = Joke.objects.create(user=drop, tangoes_purchased=9).pk
        _social(drop)
        drop_pk = drop.pk

        with mock.patch("user.discord_accounts.logger") as spy:
            merge_discord_accounts(keep=keep, drop=drop)

        rows = _discarded(spy)
        joke = [r for r in rows if r["model"] == Joke._meta.label]
        self.assertEqual(len(joke), 1)
        self.assertEqual(joke[0]["pk"], dropped_joke_pk)
        self.assertEqual(joke[0]["kept_user_id"], keep.pk)
        self.assertEqual(joke[0]["dropped_user_id"], drop_pk)
        self.assertEqual(joke[0]["system"], "auth")
        self.assertEqual(joke[0]["subsystem"], "merge")
        self.assertIn("user.BaseUserProfile", {r["model"] for r in rows})

    def test_moved_rows_are_not_logged_as_discarded(self) -> None:
        keep = CustomUser.objects.create(username="ph", discordId=DISCORD_ID)
        drop = CustomUser.objects.create(username="loginrow")
        Joke.objects.create(user=drop, tangoes_purchased=9)
        _social(drop)

        with mock.patch("user.discord_accounts.logger") as spy:
            merge_discord_accounts(keep=keep, drop=drop)

        self.assertNotIn(Joke._meta.label, {r["model"] for r in _discarded(spy)})

    def test_nickname_carried_when_kept_account_has_none(self) -> None:
        keep = CustomUser.objects.create(username="ph", discordId=DISCORD_ID)
        drop = CustomUser.objects.create(username="loginrow", nickname="Ghosty")
        _social(drop)

        merge_discord_accounts(keep=keep, drop=drop)

        self.assertEqual(
            CustomUser.objects.nocache().get(pk=keep.pk).nickname, "Ghosty"
        )

    def test_existing_nickname_kept(self) -> None:
        keep = CustomUser.objects.create(
            username="ph", discordId=DISCORD_ID, nickname="Mine"
        )
        drop = CustomUser.objects.create(username="loginrow", nickname="Theirs")
        _social(drop)

        merge_discord_accounts(keep=keep, drop=drop)

        self.assertEqual(CustomUser.objects.nocache().get(pk=keep.pk).nickname, "Mine")

    def test_positions_carried_when_kept_account_has_none_set(self) -> None:
        keep = CustomUser.objects.create(username="ph", discordId=DISCORD_ID)
        drop = CustomUser.objects.create(username="loginrow")
        _social(drop)
        drop_positions = drop.positions
        drop_positions.carry = 5
        drop_positions.mid = 3
        drop_positions.save()

        merge_discord_accounts(keep=keep, drop=drop)

        kept = CustomUser.objects.nocache().get(pk=keep.pk)
        self.assertEqual(kept.positions_id, drop_positions.pk)
        self.assertEqual((kept.positions.carry, kept.positions.mid), (5, 3))

    def test_existing_positions_kept(self) -> None:
        keep = CustomUser.objects.create(username="ph", discordId=DISCORD_ID)
        keep_positions = keep.positions
        keep_positions.offlane = 4
        keep_positions.save()
        drop = CustomUser.objects.create(username="loginrow")
        _social(drop)
        drop.positions.carry = 5
        drop.positions.save()

        merge_discord_accounts(keep=keep, drop=drop)

        kept = CustomUser.objects.nocache().get(pk=keep.pk)
        self.assertEqual(kept.positions_id, keep_positions.pk)

    def test_mmr_verification_carried_when_kept_account_unverified(self) -> None:
        verified_at = tz.now() - timedelta(days=2)
        keep = CustomUser.objects.create(username="ph", discordId=DISCORD_ID)
        drop = CustomUser.objects.create(username="loginrow")
        _social(drop)
        drop.has_active_dota_mmr = True
        drop.dota_mmr_last_verified = verified_at

        merge_discord_accounts(keep=keep, drop=drop)

        kept = CustomUser.objects.nocache().get(pk=keep.pk)
        self.assertTrue(kept.has_active_dota_mmr)
        self.assertEqual(kept.dota_mmr_last_verified, verified_at)

    def test_deadlock_rank_carried_when_kept_account_has_none(self) -> None:
        keep = CustomUser.objects.create(username="ph", discordId=DISCORD_ID)
        drop = CustomUser.objects.create(username="loginrow")
        _social(drop)
        dl = drop.base_profile.deadlock_user_profile
        dl.rank = "Archon"
        dl.rank_date = date(2026, 1, 2)
        dl.save()

        merge_discord_accounts(keep=keep, drop=drop)

        kept_dl = (
            CustomUser.objects.nocache()
            .get(pk=keep.pk)
            .base_profile.deadlock_user_profile
        )
        self.assertEqual(
            (kept_dl.rank, kept_dl.rank_date), ("Archon", date(2026, 1, 2))
        )

    def test_steam_account_carried_when_kept_account_has_none(self) -> None:
        keep = CustomUser.objects.create(username="ph", discordId=DISCORD_ID)
        drop = CustomUser.objects.create(username="loginrow", steam_account_id=123456)
        _social(drop)

        merge_discord_accounts(keep=keep, drop=drop)

        kept = CustomUser.objects.nocache().get(pk=keep.pk)
        self.assertEqual(kept.steam_account_id, 123456)
        self.assertEqual(kept.steamid, 123456 + CustomUser.STEAM_ID_64_BASE)

    def test_existing_steam_account_kept(self) -> None:
        keep = CustomUser.objects.create(
            username="ph", discordId=DISCORD_ID, steam_account_id=111
        )
        drop = CustomUser.objects.create(username="loginrow", steam_account_id=222)
        _social(drop)

        with mock.patch("user.discord_accounts.logger") as spy:
            merge_discord_accounts(keep=keep, drop=drop)

        self.assertEqual(
            CustomUser.objects.nocache().get(pk=keep.pk).steam_account_id, 111
        )
        [merged] = [
            c.kwargs
            for c in spy.info.call_args_list
            if c.args and c.args[0] == "discord_accounts_merged"
        ]
        self.assertEqual(merged["dropped_steam_account_id"], 222)


class MergeOrgMemberDependentsTest(TestCase):
    """Rows hanging off the dropped account's org membership move to the kept
    membership instead of cascading away with it."""

    def setUp(self) -> None:
        self.admin = CustomUser.objects.create(username="dep_admin")
        self.org = Organization.objects.create(name="Dep Org", owner=self.admin)
        self.league = League.objects.create(name="Dep League", organization=self.org)
        self.keep = CustomUser.objects.create(username="ph", discordId=DISCORD_ID)
        self.drop = CustomUser.objects.create(username="loginrow")
        _social(self.drop)
        self.keep_ou = OrgUser.objects.create(user=self.keep, organization=self.org)
        self.drop_ou = OrgUser.objects.create(user=self.drop, organization=self.org)

    def _team_with(self, lu: LeagueUser) -> Team:
        tournament = Tournament.objects.create(
            name="Dep Cup",
            date_played=datetime(2026, 11, 14, tzinfo=UTC),
            league=self.league,
        )
        team = Team.objects.create(tournament=tournament, name="Dep Team")
        team.league_users.add(lu)
        return team

    def test_league_membership_moves_when_kept_account_has_none(self) -> None:
        lu = LeagueUser.objects.create(
            user=self.drop, org_user=self.drop_ou, league=self.league, mmr=4200
        )

        merge_discord_accounts(keep=self.keep, drop=self.drop)

        moved = LeagueUser.objects.nocache().get(pk=lu.pk)
        self.assertEqual(
            (moved.user_id, moved.org_user_id, moved.mmr),
            (self.keep.pk, self.keep_ou.pk, 4200),
        )

    def test_conflicting_league_membership_keeps_higher_mmr_and_teams(self) -> None:
        existing = LeagueUser.objects.create(
            user=self.keep, org_user=self.keep_ou, league=self.league, mmr=3000
        )
        lu = LeagueUser.objects.create(
            user=self.drop, org_user=self.drop_ou, league=self.league, mmr=4200
        )
        team = self._team_with(lu)

        with mock.patch("user.discord_accounts.logger") as spy:
            merge_discord_accounts(keep=self.keep, drop=self.drop)

        self.assertEqual(LeagueUser.objects.nocache().get(pk=existing.pk).mmr, 4200)
        self.assertFalse(LeagueUser.objects.nocache().filter(pk=lu.pk).exists())
        self.assertEqual(
            list(team.league_users.values_list("pk", flat=True)), [existing.pk]
        )
        [row] = [r for r in _discarded(spy) if r["model"] == "league.LeagueUser"]
        self.assertEqual(row["pk"], lu.pk)

    def test_conflicting_league_membership_keeps_existing_higher_mmr(self) -> None:
        existing = LeagueUser.objects.create(
            user=self.keep, org_user=self.keep_ou, league=self.league, mmr=5000
        )
        LeagueUser.objects.create(
            user=self.drop, org_user=self.drop_ou, league=self.league, mmr=4200
        )

        merge_discord_accounts(keep=self.keep, drop=self.drop)

        self.assertEqual(LeagueUser.objects.nocache().get(pk=existing.pk).mmr, 5000)

    def test_event_dms_move_to_kept_membership(self) -> None:
        event = Event.objects.create(
            organization=self.org,
            name="Dep Event",
            scheduled_at=tz.now() + timedelta(days=3),
            state=EventState.SIGNUPS_OPEN,
            created_by=self.admin,
        )
        de = DiscordEvent.objects.create(event=event, guild_id="111")
        dm = DiscordEventDM.objects.create(
            discord_event=de,
            org_user=self.drop_ou,
            dm_type=DMType.ATTENDANCE_CONFIRM,
            responded=True,
            response_text="see you there",
        )

        merge_discord_accounts(keep=self.keep, drop=self.drop)

        kept = DiscordEventDM.objects.nocache().get(pk=dm.pk)
        self.assertEqual(
            (kept.org_user_id, kept.response_text),
            (self.keep_ou.pk, "see you there"),
        )

    def test_org_game_profile_moves_when_kept_membership_has_none(self) -> None:
        profile = PlayerDotaProfile.objects.create(
            org_user=self.drop_ou, rank_medal="Legend"
        )

        merge_discord_accounts(keep=self.keep, drop=self.drop)

        self.assertEqual(
            PlayerDotaProfile.objects.nocache().get(pk=profile.pk).org_user_id,
            self.keep_ou.pk,
        )

    def test_conflicting_org_game_profile_is_logged(self) -> None:
        kept = PlayerDotaProfile.objects.create(
            org_user=self.keep_ou, rank_medal="Archon"
        )
        dropped = PlayerDotaProfile.objects.create(
            org_user=self.drop_ou, rank_medal="Legend"
        )

        with mock.patch("user.discord_accounts.logger") as spy:
            merge_discord_accounts(keep=self.keep, drop=self.drop)

        self.assertEqual(
            PlayerDotaProfile.objects.nocache().get(org_user=self.keep_ou).pk, kept.pk
        )
        [row] = [r for r in _discarded(spy) if r["model"] == "org.PlayerDotaProfile"]
        self.assertEqual(row["pk"], dropped.pk)

    def test_merged_membership_deletion_is_logged_with_cascades(self) -> None:
        OrgUserGameMmr.objects.create(
            org_user=self.keep_ou, game_type=GameType.DOTA2, mmr=5000
        )
        OrgUserGameMmr.objects.create(
            org_user=self.drop_ou, game_type=GameType.DOTA2, mmr=4000
        )

        with mock.patch("user.discord_accounts.logger") as spy:
            merge_discord_accounts(keep=self.keep, drop=self.drop)

        [row] = [r for r in _discarded(spy) if r["model"] == "org.OrgUser"]
        self.assertEqual(row["pk"], self.drop_ou.pk)
        self.assertEqual(row["deleted"]["org.OrgUserGameMmr"], 1)

    def test_discarded_base_profile_reports_its_game_profiles(self) -> None:
        with mock.patch("user.discord_accounts.logger") as spy:
            merge_discord_accounts(keep=self.keep, drop=self.drop)

        [row] = [r for r in _discarded(spy) if r["model"] == "user.BaseUserProfile"]
        self.assertEqual(row["deleted"]["user.DotaUserProfile"], 1)
        self.assertEqual(row["deleted"]["user.DeadlockUserProfile"], 1)


class MergeProfileCarryoverCoverageTest(TestCase):
    """A field added to a user profile model must get merge carryover handling
    in user/discord_accounts.py, or be listed here as deliberately dropped."""

    def _fields(self, model: type) -> set[str]:
        return {f.name for f in model._meta.concrete_fields}

    def test_profile_fields_are_covered(self) -> None:
        self.assertEqual(
            self._fields(BaseUserProfile), {"id", "user", "nickname", "avatar"}
        )
        self.assertEqual(
            self._fields(DotaUserProfile),
            {
                "id",
                "base_profile",
                "positions",
                "has_active_dota_mmr",
                "dota_mmr_last_verified",
            },
        )
        self.assertEqual(
            self._fields(DeadlockUserProfile),
            {"id", "base_profile", "rank", "rank_date"},
        )


class MergeWithoutBaseProfileTest(TestCase):
    def test_merge_succeeds_when_neither_account_has_a_base_profile(self) -> None:
        keep = CustomUser.objects.create(username="ph", discordId=DISCORD_ID)
        drop = CustomUser.objects.create(username="loginrow")
        _social(drop)
        BaseUserProfile.objects.filter(user__in=[keep, drop]).delete()
        keep = CustomUser.objects.nocache().get(pk=keep.pk)
        drop = CustomUser.objects.nocache().get(pk=drop.pk)

        merge_discord_accounts(keep=keep, drop=drop)

        self.assertFalse(CustomUser.objects.nocache().filter(pk=drop.pk).exists())


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

    def test_phantom_leaves_synced_names_unset(self) -> None:
        from events.discord.handlers import _get_org_user

        org_user, user = _get_org_user(self.event, DISCORD_ID, discord_username="ghost")
        user.refresh_from_db()
        org_user.refresh_from_db()
        self.assertIsNone(user.discordNickname)
        self.assertIsNone(org_user.guild_nickname)

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
        self.assertEqual(CustomUser.objects.filter(discordId=DISCORD_ID).count(), 1)
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
