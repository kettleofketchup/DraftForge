from datetime import datetime
from enum import IntEnum, StrEnum
from typing import TYPE_CHECKING, Any, Self

import requests
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import QuerySet
from django.utils import timezone

from app.cache_utils import invalidate_after_commit, invalidate_obj
from common.game import GameType  # noqa: F401
from discordbot.services.member_names import normalise_name
from telemetry.logging import get_logger

if TYPE_CHECKING:
    from draft.models import DraftOptions
    from user.models import DotaUserProfile

User = settings.AUTH_USER_MODEL

log = get_logger(__name__)


class PositionsModel(models.Model):
    carry = models.IntegerField(
        default=0,
        help_text="Rank of the carry position from 0 (No play) to 5 (best)",
    )
    mid = models.IntegerField(
        default=0, help_text="Rank of the mid position from 0 (No play) to 5 (best)"
    )
    offlane = models.IntegerField(
        default=0,
        help_text="Rank of the offlane position from 0 (No play) to 5 (best)",
    )
    soft_support = models.IntegerField(
        default=0,
        help_text="Rank of the soft support position from 0 (No play) to 5 (best)",
    )
    hard_support = models.IntegerField(
        default=0,
        help_text="Rank of the hard support position from 0 (No play) to 5 (best)",
    )

    def __str__(self) -> str:
        return f"Carry: {self.carry}, Mid: {self.mid}, Offlane: {self.offlane}, Soft Support: {self.soft_support}, Hard Support: {self.hard_support}"

    def save(self, *args: object, **kwargs: object) -> None:
        super().save(*args, **kwargs)
        from app.cache_utils import invalidate_after_commit

        # T2: positions live on user.DotaUserProfile (default reverse accessor
        # dotauserprofile_set). Walk it + bubbled parents. Org positions are
        # pos_1..5 booleans on org.PlayerDotaProfile (no PositionsModel FK) —
        # cacheops auto-invalidates that model; not this loop. Org branch is T3.
        # .nocache(): invalidation must walk the live rows — a cached join
        # (invalidated only on DotaUserProfile) could miss a freshly linked
        # profile and skip its parents.
        dota_profiles = list(
            self.dotauserprofile_set.select_related("base_profile__user").nocache()
        )
        targets = []
        for dp in dota_profiles:
            targets += [dp, dp.base_profile, dp.base_profile.user]
        if targets:
            invalidate_after_commit(*targets)


# Enum for Dota2 positions
class PositionEnum(IntEnum):
    Carry = 1
    Mid = 2
    Offlane = 3
    SoftSupport = 4
    HardSupport = 5


# Team draft pick-order styles
class DraftStyles(StrEnum):
    snake = "snake"
    normal = "normal"
    shuffle = "shuffle"


class GameMode(models.TextChoices):
    NORMAL = "normal", "Normal"
    CAPTAINS_MODE = "captains_mode", "Captain's Mode"
    TURBO = "turbo", "Turbo"
    CUSTOM = "custom", "Custom Lobby"


class DotaLobbyMode(models.TextChoices):
    """Whether DraftForge asks dota_lobby for in-game lobbies (lobby app)."""

    OFF = "off", "Off"
    MANUAL = "manual", "Manual"
    AUTO = "auto", "Automatic"


class DotaLobbyLaunch(models.TextChoices):
    """dota_lobby's `launch` request field: who starts the match."""

    MANUAL = "manual", "Manual"
    AUTO = "auto", "Automatic"


class CustomUser(AbstractUser):
    # Override username to allow blank (users can be created from Steam only)
    username = models.CharField(max_length=150, unique=True, blank=True, null=True)

    # 32-bit Friend ID (Dotabuff URL) - set by user, primary identifier
    steam_account_id = models.IntegerField(null=True, unique=True, blank=True)
    # 64-bit Steam ID - auto-calculated from steam_account_id
    steamid = models.BigIntegerField(null=True, blank=True, db_index=True)

    @property
    def needs_mmr_verification(self) -> bool:
        """Check if user needs to verify their MMR (>30 days since last verification)."""
        if not self.has_active_dota_mmr:
            return False
        if self.dota_mmr_last_verified is None:
            return True
        days_since = (timezone.now() - self.dota_mmr_last_verified).days
        return days_since > 30

    discordId = models.TextField(null=True, unique=True, blank=True)
    discordUsername = models.TextField(null=True, blank=True)
    discordNickname = models.TextField(null=True, blank=True)
    # deprecated: replaced by OrgUser.guild_nickname; dropped in a later release
    guildNickname = models.TextField(null=True, blank=True)
    default_organization = models.ForeignKey(
        "org.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="default_for_users",
    )

    # Steam ID conversion constant
    # steamid (64-bit) = steam_account_id (32-bit) + STEAM_ID_64_BASE
    STEAM_ID_64_BASE = 76561197960265728

    @property
    def nickname(self) -> str | None:
        """Transitional proxy — reads nickname from base_profile.

        Remove once all writers migrate to PATCH /api/users/me/profile/base/.
        """
        bp = getattr(self, "base_profile", None)
        if bp is None:
            # Pre-pk: return the value buffered by the setter so set-then-read
            # before save() works (matches the old column's behavior).
            return getattr(self, "_pending_nickname", None)
        return bp.nickname

    @nickname.setter
    def nickname(self, value: str | None) -> None:
        """Transitional setter — writes through to base_profile.nickname.

        Persists immediately so populate fixtures and incidental writers
        behave as if the field were still on CustomUser. Invalidates the
        base_profile cacheops row on commit.
        """
        # Use a local import to avoid the circular at module load.
        from app.cache_utils import invalidate_after_commit

        bp = getattr(self, "base_profile", None)
        if bp is None:
            # User hasn't been saved yet (no pk) — buffer the value and apply
            # in save() after auto-create.
            self._pending_nickname = value
            return
        bp.nickname = value
        bp.save(update_fields=["nickname"])
        invalidate_after_commit(bp)

    @property
    def avatar(self) -> str | None:
        bp = getattr(self, "base_profile", None)
        if bp is None:
            return getattr(self, "_pending_avatar", None)
        return bp.avatar

    @avatar.setter
    def avatar(self, value: str | None) -> None:
        from app.cache_utils import invalidate_after_commit

        bp = getattr(self, "base_profile", None)
        if bp is None:
            self._pending_avatar = value
            return
        bp.avatar = value
        bp.save(update_fields=["avatar"])
        invalidate_after_commit(bp)

    @property
    def dota_user_profile(self) -> "DotaUserProfile | None":
        """Convenience accessor — the user-wide Dota profile lives one hop
        away on base_profile. Transitional sugar for the shims below and
        writers still phrasing reads as `user.dota_user_profile`. None-safe
        like the shims: a pre-pk user (no base_profile yet) returns None
        instead of raising RelatedObjectDoesNotExist."""
        bp = getattr(self, "base_profile", None)
        return getattr(bp, "dota_user_profile", None) if bp else None

    @property
    def positions(self) -> PositionsModel | None:
        """Transitional proxy — reads positions from dota_user_profile.
        Remove once writers migrate to PATCH /api/users/me/profile/game/dota/."""
        bp = getattr(self, "base_profile", None)
        dp = getattr(bp, "dota_user_profile", None) if bp else None
        return dp.positions if dp else None

    @positions.setter
    def positions(self, value: PositionsModel | None) -> None:
        from app.cache_utils import invalidate_after_commit

        bp = getattr(self, "base_profile", None)
        dp = getattr(bp, "dota_user_profile", None) if bp else None
        if dp is None:
            self._pending_positions = value
            return
        dp.positions = value
        dp.save(update_fields=["positions"])
        invalidate_after_commit(dp)

    @property
    def positions_id(self) -> int | None:
        bp = getattr(self, "base_profile", None)
        dp = getattr(bp, "dota_user_profile", None) if bp else None
        return dp.positions_id if dp else None

    @property
    def has_active_dota_mmr(self) -> bool:
        bp = getattr(self, "base_profile", None)
        dp = getattr(bp, "dota_user_profile", None) if bp else None
        return dp.has_active_dota_mmr if dp else False

    @has_active_dota_mmr.setter
    def has_active_dota_mmr(self, value: bool) -> None:
        from app.cache_utils import invalidate_after_commit

        bp = getattr(self, "base_profile", None)
        dp = getattr(bp, "dota_user_profile", None) if bp else None
        if dp is None:
            self._pending_has_active_dota_mmr = value
            return
        dp.has_active_dota_mmr = value
        dp.save(update_fields=["has_active_dota_mmr"])
        invalidate_after_commit(dp)

    @property
    def dota_mmr_last_verified(self) -> datetime | None:
        bp = getattr(self, "base_profile", None)
        dp = getattr(bp, "dota_user_profile", None) if bp else None
        return dp.dota_mmr_last_verified if dp else None

    @dota_mmr_last_verified.setter
    def dota_mmr_last_verified(self, value: datetime | None) -> None:
        from app.cache_utils import invalidate_after_commit

        bp = getattr(self, "base_profile", None)
        dp = getattr(bp, "dota_user_profile", None) if bp else None
        if dp is None:
            self._pending_dota_mmr_last_verified = value
            return
        dp.dota_mmr_last_verified = value
        dp.save(update_fields=["dota_mmr_last_verified"])
        invalidate_after_commit(dp)

    def createFromDiscordData(self, data: dict[str, Any]) -> Self:
        self.username = data["user"]["username"]
        self.discordId = data["user"]["id"]
        self.avatar = data["user"]["avatar"]
        self.discordUsername = data["user"]["username"]
        self.discordNickname = normalise_name(data["user"].get("global_name"))
        # Use server nick first, then global_name, then username (always present)
        self.nickname = (
            data.get("nick")
            or data["user"].get("global_name")
            or data["user"]["username"]
        )
        return self

    def check_and_update_avatar(self) -> bool:
        """
        Checks if the current avatar URL is valid. If not, fetches the latest
        avatar from Discord and updates the database.

        Returns:
            bool: True if the avatar was updated, False otherwise.
        """
        if not self.discordId:
            return False

        if not self.avatar:
            # If no avatar is set, try to fetch one.
            return self._fetch_and_update_avatar_from_discord()

        # Construct current avatar URL
        extension = "gif" if self.avatar.startswith("a_") else "png"
        current_url = f"https://cdn.discordapp.com/avatars/{self.discordId}/{self.avatar}.{extension}"

        if self._is_avatar_url_valid(current_url):
            return False

        return self._fetch_and_update_avatar_from_discord()

    def _is_avatar_url_valid(self, url: str) -> bool:
        """
        Check if the avatar URL returns a valid response (not 404).
        """
        try:
            response = requests.head(url, timeout=5)
            return response.status_code == 200
        except requests.RequestException:
            log.warning(
                "avatar_url_validation_failed",
                system="tournament",
                subsystem="user",
                username=self.username,
                url=url,
            )
            return False

    def _fetch_and_update_avatar_from_discord(self) -> bool:
        """
        Fetch the latest avatar from Discord API and update the database.

        Returns:
            bool: True if avatar was updated, False otherwise.
        """
        if not self.discordId:
            return False

        # Skip if Discord bot token is not configured (e.g., in CI)
        discord_bot_token = getattr(settings, "DISCORD_BOT_TOKEN", None)
        if not discord_bot_token:
            log.debug(
                "avatar_fetch_skipped",
                system="tournament",
                subsystem="user",
                username=self.username,
                reason="DISCORD_BOT_TOKEN not configured",
            )
            return False

        try:
            headers = {
                "Authorization": f"Bot {discord_bot_token}",
            }
            response = requests.get(
                f"{settings.DISCORD_API_BASE_URL}/users/{self.discordId}",
                headers=headers,
                timeout=10,
            )

            if response.status_code == 200:
                user_data = response.json()
                new_avatar = user_data.get("avatar")

                if new_avatar != self.avatar:
                    # The avatar setter persists to base_profile.avatar via
                    # bp.save(update_fields=["avatar"]) inside the setter, so
                    # an explicit CustomUser.save(update_fields=["avatar"])
                    # here would crash now that `avatar` is a property, not a
                    # model field.
                    self.avatar = new_avatar
                    log.info(
                        "avatar_updated",
                        system="tournament",
                        subsystem="user",
                        username=self.username,
                        discord_id=self.discordId,
                    )
                    return True
                return False

            else:
                log.warning(
                    "avatar_fetch_failed",
                    system="tournament",
                    subsystem="user",
                    username=self.username,
                    status_code=response.status_code,
                )
                return False

        except requests.RequestException as e:
            log.error(
                "avatar_fetch_error",
                system="tournament",
                subsystem="user",
                username=self.username,
                error=str(e),
            )
            return False
        except Exception as e:
            log.error(
                "avatar_update_unexpected_error",
                system="tournament",
                subsystem="user",
                username=self.username,
                error=str(e),
            )
            return False

    def save(self, *args: object, **kwargs: object) -> None:
        """Keep steam ids in sync, auto-create BaseUserProfile (which in turn
        auto-creates the game profiles + default positions), invalidate
        cacheops, and flush pending nickname/avatar/positions/mmr values
        buffered by the transitional property setters before the user had a pk.

        Keep this the only save() on CustomUser: a second definition in the
        class body silently replaces this one, dropping the steam id sync.
        """
        # 1. Steam id 32-bit / 64-bit sync.
        if self.steam_account_id is not None:
            self.steamid = self.steam_account_id + self.STEAM_ID_64_BASE
        elif self.steamid is not None:
            self.steam_account_id = self.steamid - self.STEAM_ID_64_BASE
        else:
            self.steamid = None
            self.steam_account_id = None

        super().save(*args, **kwargs)
        # Cacheops auto-fires invalidation for `self` via post_save signal
        # (model is registered with ops="all"). No explicit call needed.

        # 2. BaseUserProfile auto-create. Idempotent via get_or_create.
        # Local import avoids the circular: user.models -> app.CustomUser.
        from user.models import BaseUserProfile

        bp, _ = BaseUserProfile.objects.get_or_create(user=self)

        # 3. Flush pending nickname/avatar values buffered by the property
        #    setters before the user had a pk (and therefore a base_profile).
        #    Hold the `del` until bp.save() succeeds so a retry after a
        #    transient DB error still has the buffered value to flush.
        pending_nickname = getattr(self, "_pending_nickname", None)
        pending_avatar = getattr(self, "_pending_avatar", None)
        fields_to_update = []
        if pending_nickname is not None:
            bp.nickname = pending_nickname
            fields_to_update.append("nickname")
        if pending_avatar is not None:
            bp.avatar = pending_avatar
            fields_to_update.append("avatar")
        if fields_to_update:
            from app.cache_utils import invalidate_after_commit

            bp.save(update_fields=fields_to_update)
            invalidate_after_commit(bp)
            if pending_nickname is not None:
                del self._pending_nickname
            if pending_avatar is not None:
                del self._pending_avatar

        # 4. Flush pending positions/mmr buffered by the shims pre-pk.
        dp = bp.dota_user_profile
        dota_fields = []
        if hasattr(self, "_pending_positions"):
            dp.positions = self._pending_positions
            dota_fields.append("positions")
        if hasattr(self, "_pending_has_active_dota_mmr"):
            dp.has_active_dota_mmr = self._pending_has_active_dota_mmr
            dota_fields.append("has_active_dota_mmr")
        if hasattr(self, "_pending_dota_mmr_last_verified"):
            dp.dota_mmr_last_verified = self._pending_dota_mmr_last_verified
            dota_fields.append("dota_mmr_last_verified")
        if dota_fields:
            from app.cache_utils import invalidate_after_commit

            dp.save(update_fields=dota_fields)
            invalidate_after_commit(dp)
            for attr in (
                "_pending_positions",
                "_pending_has_active_dota_mmr",
                "_pending_dota_mmr_last_verified",
            ):
                if hasattr(self, attr):
                    delattr(self, attr)

    @property
    def avatarUrl(self) -> str | None:
        """
        Constructs the Discord avatar URL from the stored discordId and avatar hash.
        This property does not perform any network requests.
        """
        if not self.discordId:
            return None

        if self.avatar:
            extension = "gif" if self.avatar.startswith("a_") else "png"
            return f"https://cdn.discordapp.com/avatars/{self.discordId}/{self.avatar}.{extension}"

        # Default avatar logic
        if self.discordId:
            # New default avatar URL logic based on user ID
            return f"https://cdn.discordapp.com/embed/avatars/{(int(self.discordId) >> 22) % 6}.png"

        return "https://cdn.discordapp.com/embed/avatars/0.png"  # Fallback

    class Meta:
        indexes = [
            models.Index(fields=["discordNickname"]),
            models.Index(fields=["guildNickname"]),
            models.Index(fields=["discordUsername"]),
        ]


TOURNAMNET_TYPE_CHOICES = [
    ("single_elimination", "Single Elimination"),
    ("double_elimination", "Double Elimination"),
    ("swiss", "Swiss Bracket"),
]


class Tournament(models.Model):
    STATE_CHOICES = [
        ("future", "Future"),
        ("in_progress", "In Progress"),
        ("past", "Past"),
    ]
    name = models.CharField(max_length=255)
    date_played = models.DateTimeField(
        help_text="Tournament date and time (stored in UTC)"
    )
    timezone = models.CharField(
        max_length=50,
        default="UTC",
        help_text="Tournament timezone (e.g., 'America/New_York', 'Europe/London')",
    )
    users = models.ManyToManyField(User, related_name="tournaments")
    # teams: reverse accessor of Team.tournament
    winning_team = models.OneToOneField(
        "Team",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tournaments_won",
    )

    state = models.CharField(max_length=20, choices=STATE_CHOICES, default="future")
    tournament_type = models.CharField(
        max_length=30, choices=TOURNAMNET_TYPE_CHOICES, default="double_elimination"
    )

    steam_league_id = models.IntegerField(
        null=True,
        blank=True,
        default=None,
        help_text="Steam league ID for match linking",
        db_column="league_id",  # Keep existing column name for backwards compatibility
    )
    league = models.ForeignKey(
        "league.League",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tournaments",
        db_column="league_fk_id",
    )

    game_type = models.IntegerField(
        choices=GameType.choices,
        default=GameType.DOTA2,
    )
    draft_type = models.CharField(
        max_length=10,
        choices=[(s.value, s.value.title()) for s in DraftStyles],
        default=DraftStyles.shuffle.value,
    )
    people_per_team = models.IntegerField(default=5)
    number_of_teams = models.IntegerField(null=True, blank=True)
    game_mode = models.CharField(
        max_length=20, choices=GameMode.choices, default=GameMode.NORMAL
    )
    custom_game_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Custom game/lobby name (for custom game mode)",
    )
    captains_draft_time = models.IntegerField(
        default=10,
        help_text="Seconds per draft pick in Captain's Mode",
    )
    lobby_steam_league_id = models.IntegerField(
        null=True,
        blank=True,
        help_text="Steam league ID for Dota 2 lobby ticket",
    )
    auto_create_hero_drafts = models.BooleanField(default=False)
    discord_send_draft_link = models.BooleanField(default=True)
    discord_send_herodraft_link = models.BooleanField(default=True)
    # dota_lobby integration (lobby app). Off by default; the global
    # DOTA_LOBBY_ENABLED setting must also be on.
    dota_lobby_mode = models.CharField(
        max_length=8, choices=DotaLobbyMode.choices, default=DotaLobbyMode.OFF
    )
    dota_lobby_launch = models.CharField(
        max_length=8, choices=DotaLobbyLaunch.choices, default=DotaLobbyLaunch.MANUAL
    )
    dota_lobby_region = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="dota_lobby region name; empty uses DOTA_LOBBY_REGION",
    )
    discord_send_lobby_info = models.BooleanField(
        default=False,
        help_text="DM rostered players the lobby name and password",
    )
    # The password of every lobby created for this tournament: copied from
    # the source event, or generated for a standalone tournament once lobbies
    # are enabled (lobby.passwords). Never in public serializers.
    dota_lobby_password = models.CharField(max_length=32, blank=True, default="")

    def __str__(self) -> str:
        return self.name

    def save(self, *args: object, **kwargs: object) -> None:
        if self.dota_lobby_mode != DotaLobbyMode.OFF and not self.dota_lobby_password:
            from lobby.passwords import generate_password

            self.dota_lobby_password = generate_password()
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                kwargs["update_fields"] = {*update_fields, "dota_lobby_password"}
        super().save(*args, **kwargs)
        # Self-invalidation handled by cacheops post_save signal; the
        # cascade to league + org refreshes those parents' embedded
        # tournament list. Targeted invalidate_obj() rather than
        # invalidate_model() so unrelated tournaments stay cached.
        if self.league:
            invalidate_obj(self.league)
            if self.league.organization:
                invalidate_obj(self.league.organization)

    class Meta:
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["-date_played"]),
            models.Index(fields=["state"]),
            models.Index(fields=["league"]),
        ]

    @property
    def captains(self) -> "list[CustomUser] | QuerySet[CustomUser]":
        """
        Returns all users who are captains in this tournament.
        This is used to populate the draft choices.
        """
        if not self.users.exists():
            return []
        if not self.teams.exists():
            return []
        return self.users.filter(teams_as_captain__tournament=self).distinct()

    def draft_eligible_teams(self) -> "QuerySet[Team]":
        """Teams whose captain is in the tournament's player pool.

        Not cached: cacheops does not invalidate on subquery tables.
        """
        return self.teams.nocache().filter(captain_id__in=self.users.values("pk"))

    def draft_ineligible_teams(self) -> "QuerySet[Team]":
        return self.teams.nocache().exclude(
            pk__in=self.draft_eligible_teams().values("pk")
        )

    def draft_locked_user_ids(self) -> "QuerySet[CustomUser]":
        """Members of teams outside the draft; they are not draftable."""
        return (
            CustomUser.objects.nocache()
            .filter(teams_as_member__in=self.draft_ineligible_teams())
            .values("pk")
        )

    @property
    def linked_steam_league_id(self) -> int | None:
        """Steam league id resolved via the parent League FK.

        The legacy `Tournament.steam_league_id` field is ignored. Callers doing
        Steam match lookups should use this property so behavior follows
        the linked League and edits to League.steam_league_id take effect
        without per-tournament duplication.
        """
        if not self.league_id:
            return None
        return self.league.steam_league_id

    def get_draft_options(self, *, fresh: bool = False) -> "DraftOptions":
        options_model = self._meta.get_field("draft_options").related_model
        manager = options_model.objects.nocache() if fresh else options_model.objects
        options, _ = manager.get_or_create(tournament=self)
        return options


class LeadershipProblem(StrEnum):
    CAPTAIN_NOT_MEMBER = "captain_not_member"
    DEPUTY_NOT_MEMBER = "deputy_not_member"
    DEPUTY_IS_CAPTAIN = "deputy_is_captain"

    @property
    def message(self) -> str:
        return _LEADERSHIP_MESSAGES[self]


_LEADERSHIP_MESSAGES: dict[LeadershipProblem, str] = {
    LeadershipProblem.CAPTAIN_NOT_MEMBER: "Captain must be a member of the team.",
    LeadershipProblem.DEPUTY_NOT_MEMBER: "Deputy captain must be a member of the team.",
    LeadershipProblem.DEPUTY_IS_CAPTAIN: "Deputy captain cannot be the same as captain.",
}


class Team(models.Model):
    tournament = models.ForeignKey(
        Tournament,
        related_name="teams",
        on_delete=models.CASCADE,
        null=True,  # Allow null for legacy data/migrations
        blank=True,
    )
    name = models.CharField(max_length=255)
    captain = models.ForeignKey(
        User,
        related_name="teams_as_captain",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    deputy_captain = models.ForeignKey(
        User,
        related_name="teams_as_deputy_captain",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        help_text="Next in line for captain if captain is removed",
    )
    draft_order = models.PositiveSmallIntegerField(
        default=0,
        blank=True,
        null=True,
        help_text="Order in which a team picks their players in the draft",
    )
    members = models.ManyToManyField(User, related_name="teams_as_member", blank=True)
    dropin_members = models.ManyToManyField(
        User, related_name="teams_as_dropin", blank=True
    )
    left_members = models.ManyToManyField(
        User, related_name="teams_as_left", blank=True
    )

    # LeagueUser-based membership (org-scoped MMR system)
    league_users = models.ManyToManyField(
        "league.LeagueUser",
        related_name="teams",
        blank=True,
        help_text="Team members as LeagueUser (for org-scoped MMR)",
    )

    current_points = models.IntegerField(default=0, blank=True)
    placement = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Final tournament placement (1=winner, 2=runner-up, etc.)",
    )

    draft_reserve_ms = models.IntegerField(null=True, blank=True)
    draft_is_ready = models.BooleanField(default=False)
    draft_is_connected = models.BooleanField(default=False)
    draft_has_connected = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["tournament"]),
            models.Index(fields=["name"]),
            models.Index(fields=["captain"]),
            models.Index(fields=["deputy_captain"]),
        ]

    @staticmethod
    def leadership_errors(
        member_pks: set[int],
        captain_pk: int | None,
        deputy_pk: int | None,
        *,
        check_captain: bool = True,
        check_deputy: bool = True,
    ) -> dict[str, str]:
        problems = Team.leadership_problems(
            member_pks,
            captain_pk,
            deputy_pk,
            check_captain=check_captain,
            check_deputy=check_deputy,
        )
        return {field: problem.message for field, problem in problems.items()}

    @staticmethod
    def leadership_problems(
        member_pks: set[int],
        captain_pk: int | None,
        deputy_pk: int | None,
        *,
        check_captain: bool = True,
        check_deputy: bool = True,
    ) -> dict[str, "LeadershipProblem"]:
        problems: dict[str, LeadershipProblem] = {}
        if check_captain and captain_pk is not None and captain_pk not in member_pks:
            problems["captain"] = LeadershipProblem.CAPTAIN_NOT_MEMBER
        if check_deputy and deputy_pk is not None and deputy_pk not in member_pks:
            problems["deputy_captain"] = LeadershipProblem.DEPUTY_NOT_MEMBER
        elif deputy_pk is not None and deputy_pk == captain_pk:
            problems["deputy_captain"] = LeadershipProblem.DEPUTY_IS_CAPTAIN
        return problems

    def replace_member(self, old: CustomUser, new: CustomUser) -> None:
        was_member = self.members.filter(pk=old.pk).exists()
        if was_member:
            self.members.add(new)
        update_fields: list[str] = []
        if self.captain_id == old.pk:
            self.captain = new
            update_fields.append("captain")
        if self.deputy_captain_id == old.pk:
            self.deputy_captain = new
            update_fields.append("deputy_captain")
        if (
            self.deputy_captain_id is not None
            and self.deputy_captain_id == self.captain_id
        ):
            self.deputy_captain = None
            update_fields.append("deputy_captain")
        if update_fields:
            self.save(update_fields=sorted(set(update_fields)))
        if was_member:
            self.members.remove(old)
        invalidate_after_commit(self, old, new)

    def reduce_members_to_captain(self) -> list[CustomUser]:
        """Leave only the captain as a member; returns the removed members.

        Add before remove: removing first can empty a team whose captain is
        not a member, and the removal signal then deletes it with its games.
        """
        if self.captain_id is None:
            raise ValueError(f"Team {self.pk} has no captain to reset to.")
        self.members.add(self.captain_id)
        removed = list(self.members.exclude(pk=self.captain_id))
        if removed:
            self.members.remove(*removed)
        return removed

    def reset_to_captain(self) -> list[CustomUser]:
        """Reset the team in place for a fresh draft; returns the removed members."""
        removed = self.reduce_members_to_captain()
        self.dropin_members.clear()
        self.left_members.clear()
        league = self.tournament.league if self.tournament_id else None
        self.league_users.set(
            self.league_users.model.objects.filter(
                user_id=self.captain_id, league=league
            )
            if league
            else []
        )
        self.deputy_captain = None
        self.draft_reserve_ms = None
        self.draft_is_ready = False
        self.draft_is_connected = False
        self.draft_has_connected = False
        self.current_points = self._meta.get_field("current_points").get_default()
        self.placement = self._meta.get_field("placement").get_default()
        self.save(
            update_fields=[
                "deputy_captain",
                "draft_reserve_ms",
                "draft_is_ready",
                "draft_is_connected",
                "draft_has_connected",
                "current_points",
                "placement",
            ]
        )
        invalidate_after_commit(self, *removed, self.captain)
        return removed

    def clean(self) -> None:
        super().clean()

        # Skip ManyToMany validation if team has no pk yet (being created)
        if not self.pk:
            return

        errors = Team.leadership_errors(
            set(self.members.values_list("pk", flat=True)),
            self.captain_id,
            self.deputy_captain_id,
        )
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return self.name

    @property
    def games(self) -> "QuerySet[Game]":
        return Game.objects.filter(
            models.Q(radiant_team=self) | models.Q(dire_team=self)
        )


class Game(models.Model):
    tournament = models.ForeignKey(
        Tournament,
        related_name="games",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    league = models.ForeignKey(
        "league.League",
        related_name="games",
        on_delete=models.CASCADE,
        null=True,
        blank=True,  # Games can belong directly to a league
    )
    round = models.IntegerField(default=1)

    # Bracket positioning fields
    bracket_type = models.CharField(
        max_length=20,
        choices=[
            ("winners", "Winners Bracket"),
            ("losers", "Losers Bracket"),
            ("grand_finals", "Grand Finals"),
            ("swiss", "Swiss"),
        ],
        default="winners",
    )
    elimination_type = models.CharField(
        max_length=10,
        choices=[
            ("single", "Single Elimination"),
            ("double", "Double Elimination"),
            ("swiss", "Swiss"),
        ],
        default="double",
        help_text="single=loser out, double=loser drops to losers bracket, swiss=record-based",
    )
    position = models.IntegerField(
        default=0, help_text="Position within round (0-indexed)"
    )

    # Match flow - which game winner advances to
    next_game = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="source_games",
    )
    next_game_slot = models.CharField(
        max_length=10,
        choices=[("radiant", "Radiant"), ("dire", "Dire")],
        null=True,
        blank=True,
    )

    # Loser path (for double elimination)
    loser_next_game = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="loser_source_games",
        help_text="Game where loser advances to (for double elim rounds)",
    )
    loser_next_game_slot = models.CharField(
        max_length=10,
        choices=[("radiant", "Radiant"), ("dire", "Dire")],
        null=True,
        blank=True,
    )

    # Swiss format tracking
    swiss_record_wins = models.IntegerField(
        default=0, help_text="Team's wins entering this match (Swiss format)"
    )
    swiss_record_losses = models.IntegerField(
        default=0, help_text="Team's losses entering this match (Swiss format)"
    )

    # Match status
    status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("live", "Live"),
            ("completed", "Completed"),
        ],
        default="pending",
    )

    # Steam match ID if it exists (64-bit)
    gameid = models.BigIntegerField(null=True, blank=True)

    radiant_team = models.ForeignKey(
        Team,
        related_name="games_as_radiant",
        null=True,
        on_delete=models.CASCADE,
        blank=True,
    )
    dire_team = models.ForeignKey(
        Team,
        related_name="games_as_dire",
        null=True,
        on_delete=models.CASCADE,
        blank=True,
    )
    winning_team = models.ForeignKey(
        Team, related_name="games_won", null=True, on_delete=models.CASCADE, blank=True
    )

    def __str__(self) -> str:
        tourn_name = self.tournament.name if self.tournament else "No Tournament"
        radiant = self.radiant_team.name if self.radiant_team else "TBD"
        dire = self.dire_team.name if self.dire_team else "TBD"
        return f"{radiant} vs {dire} in {tourn_name}"

    @property
    def teams(self) -> list[Team | None]:
        return [self.radiant_team, self.dire_team]

    class Meta:
        indexes = [
            models.Index(fields=["tournament"]),
            models.Index(fields=["league"]),
            models.Index(fields=["status"]),
            models.Index(fields=["gameid"]),
            models.Index(fields=["radiant_team"]),
            models.Index(fields=["dire_team"]),
        ]

    def save(self, *args: object, **kwargs: object) -> None:
        super().save(*args, **kwargs)
        # Self-invalidation via cacheops post_save signal. Explicit
        # cascade keeps the tournament/league cached team lists fresh.
        if self.tournament_id:
            invalidate_obj(self.tournament)
        if self.league_id:
            invalidate_obj(self.league)


class Joke(models.Model):
    """Tracks joke-related data per user (tangoes purchased, etc.)."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="joke")
    tangoes_purchased = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Joke"
        verbose_name_plural = "Jokes"

    def __str__(self) -> str:
        return f"{self.user.username} - {self.tangoes_purchased} tangoes"


class TeamLogVia(models.TextChoices):
    WEB = "web", "Web"
    DISCORD = "discord", "Discord"
    API = "api", "API"
    SYSTEM = "system", "System"


class TeamLogAction(models.TextChoices):
    SET_CAPTAIN = "set_captain", "Set Captain"
    SET_DEPUTY = "set_deputy", "Set Deputy"
    MARK_DROPOUT = "mark_dropout", "Mark Dropout"
    RESTORE_MEMBER = "restore_member", "Restore Member"
    ADD_STANDIN = "add_standin", "Add Stand-in"
    REMOVE_STANDIN = "remove_standin", "Remove Stand-in"
    SUB_IN = "sub_in", "Sub In"
    RENAME = "rename", "Rename"
    LEGACY_PATCH = "legacy_patch", "Legacy Patch"
    SYSTEM_SUCCESSION = "system_succession", "System Succession"
    EMPTY_TEAM_KEPT = "empty_team_kept", "Empty Team Kept"
    TEAM_DELETED = "team_deleted", "Team Deleted"
    MATERIALIZE = "materialize", "Materialize"


class TeamLog(models.Model):
    """Append-only audit of staff and system team roster changes."""

    team = models.ForeignKey(
        Team,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="logs",
    )
    event_team = models.ForeignKey(
        "events.EventTeam",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="team_logs",
    )
    team_snapshot_id = models.PositiveIntegerField(null=True, blank=True)
    tournament_id = models.PositiveIntegerField(null=True, blank=True)
    event_id = models.PositiveIntegerField(null=True, blank=True)
    organization_id = models.PositiveIntegerField(null=True, blank=True)
    occasion_at = models.DateTimeField(null=True, blank=True)
    team_name = models.CharField(max_length=255, blank=True)
    actor = models.ForeignKey(
        "CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        related_name="team_actions_performed",
    )
    via = models.CharField(max_length=16, choices=TeamLogVia.choices)
    action = models.CharField(max_length=32, choices=TeamLogAction.choices)
    target_user = models.ForeignKey(
        "CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="team_actions_received",
    )
    reason = models.TextField(blank=True)
    override_rules = models.JSONField(default=list, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["team_snapshot_id", "-created_at"]),
            models.Index(fields=["event_id", "-created_at"]),
            models.Index(fields=["tournament_id", "-created_at"]),
        ]
        verbose_name = "Team Log"
        verbose_name_plural = "Team Logs"

    def __str__(self) -> str:
        actor_name = self.actor.username if self.actor else "System"
        return f"{actor_name} {self.action} on {self.team_name}"


class ProfileClaimRequest(models.Model):
    """
    Request to claim a profile (merge a Steam-only profile into a Discord account).

    Flow:
    1. User with Discord ID sees profile with Steam ID but no Discord
    2. User clicks "Claim" which creates a pending request
    3. Org admin reviews and approves/rejects
    4. If approved, the merge happens and target profile is deleted
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    claimer = models.ForeignKey(
        "CustomUser",
        on_delete=models.CASCADE,
        related_name="claim_requests_made",
        help_text="User requesting to claim the profile (has Discord ID)",
    )
    target_user = models.ForeignKey(
        "CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        related_name="claim_requests_received",
        help_text="Profile being claimed (has Steam ID, no Discord). NULL after merge.",
    )
    organization = models.ForeignKey(
        "org.Organization",
        on_delete=models.CASCADE,
        related_name="claim_requests",
        help_text="Organization where the target profile is a member",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    reviewed_by = models.ForeignKey(
        "CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="claim_requests_reviewed",
        help_text="Admin who approved/rejected the request",
    )
    rejection_reason = models.TextField(
        blank=True,
        help_text="Reason for rejection (if rejected)",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "status", "-created_at"]),
            models.Index(fields=["claimer", "status"]),
        ]
        # Prevent duplicate pending requests for same claimer+target
        constraints = [
            models.UniqueConstraint(
                fields=["claimer", "target_user"],
                condition=models.Q(status="pending"),
                name="unique_pending_claim_request",
            )
        ]

    def __str__(self) -> str:
        return f"{self.claimer.username} -> {self.target_user.nickname or self.target_user.steamid} ({self.status})"
