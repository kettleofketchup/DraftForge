from datetime import datetime
from typing import TYPE_CHECKING, Any, Self

import requests
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from app.cache_utils import invalidate_after_commit
from common.game import GameType  # noqa: F401
from discordbot.services.member_names import normalise_name
from telemetry.logging import get_logger

if TYPE_CHECKING:
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
        # Positions live on user.DotaUserProfile (default reverse accessor
        # dotauserprofile_set). Walk it + bubbled parents. Org positions are
        # pos_1..5 booleans on org.PlayerDotaProfile (no PositionsModel FK) —
        # cacheops auto-invalidates that model; not this loop.
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


class CustomUser(AbstractUser):
    # Override username to allow blank (users can be created from Steam only)
    username = models.CharField(max_length=150, unique=True, blank=True, null=True)

    # 32-bit Friend ID (Dotabuff URL) - set by user, primary identifier.
    # Unsigned 32-bit, so wider than IntegerField.
    steam_account_id = models.BigIntegerField(null=True, unique=True, blank=True)
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
        # local: user app is not in celery MODEL_APPS
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
