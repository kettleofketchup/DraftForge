"""Opt-in audience fixtures for the org-features sequential E2E project."""

from datetime import timedelta
from typing import Any, Final

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from app.cache_utils import invalidate_obj
from app.models import CustomUser
from events.constants import SignupStatus
from events.models import Event, EventSignup
from org.models import Organization, OrgUser, PromoSend
from tests.data.org_features import OF_PROMOTER, ORG_FEATURES_DISCORD_BASE
from user.models import PositionsModel

GUILD_ID: Final[str] = "730000000000009901"
_original_discord_settings: tuple[str | None, str] | None = None


def restore_promotion_audience_settings() -> None:
    global _original_discord_settings
    if _original_discord_settings is not None:
        settings.DISCORD_BOT_TOKEN, settings.DISCORD_API_BASE_URL = (
            _original_discord_settings
        )
        _original_discord_settings = None
    cache.delete(f"discord_members_{GUILD_ID}")
    CustomUser.objects.filter(
        discordId__in=[str(ORG_FEATURES_DISCORD_BASE + pk) for pk in range(7380, 7390)]
    ).delete()


# key, age in days, linked account, bot
MEMBERS: Final[tuple[tuple[str, int, bool, bool], ...]] = (
    ("fresh", 2, True, False),
    ("week", 10, True, False),
    ("month", 20, True, False),
    ("quarter", 60, True, False),
    ("old", 100, True, False),
    ("signed", 3, True, False),
    ("messaged", 4, True, False),
    ("declined", 5, True, False),
    ("unlinked", 1, False, False),
    ("bot", 1, False, True),
)


def seed_promotion_audiences(org: Organization, event: Event) -> dict[str, Any]:
    global _original_discord_settings
    if _original_discord_settings is None:
        _original_discord_settings = (
            settings.DISCORD_BOT_TOKEN,
            settings.DISCORD_API_BASE_URL,
        )
    settings.DISCORD_BOT_TOKEN = "audience-e2e-cache-only"
    settings.DISCORD_API_BASE_URL = "http://127.0.0.1:9"
    now = timezone.now()
    org.discord_server_id = GUILD_ID
    org.save(update_fields=["discord_server_id"])
    members: list[dict[str, Any]] = []
    refs: dict[str, Any] = {}
    activity = Event.objects.create(
        organization=org,
        name="Audience activity history",
        scheduled_at=now - timedelta(days=110),
    )
    for index, (key, age, linked, bot) in enumerate(MEMBERS):
        pk = 7380 + index
        discord_id = str(ORG_FEATURES_DISCORD_BASE + pk)
        if not linked:
            CustomUser.objects.filter(discordId=discord_id).delete()
        user: CustomUser | None = None
        if linked:
            user = CustomUser.objects.filter(pk=pk).first()
            if user is None:
                user = CustomUser(pk=pk, positions=PositionsModel.objects.create())
                user.set_unusable_password()
            user.username = f"audience_{key}"
            user.discordId = discord_id
            user.discordUsername = f"handle_{key}"
            user.discordNickname = f"Global {key}"
            user.save()
            OrgUser.objects.update_or_create(
                organization=org,
                user=user,
                defaults={"guild_nickname": f"Guild {key}"},
            )
            signup = EventSignup.objects.create(
                event=activity,
                user=user,
                status=SignupStatus.APPROVED,
            )
            EventSignup.objects.filter(pk=signup.pk).update(
                signed_up_at=now - timedelta(days=age),
            )
        members.append(
            {
                "user": {
                    "id": discord_id,
                    "username": f"handle_{key}",
                    "global_name": f"Global {key}",
                    "bot": bot,
                    "avatar": None,
                },
                "nick": f"Guild {key}",
                "joined_at": (now - timedelta(days=age)).isoformat(),
            }
        )
        refs[key] = {"pk": user.pk if user else None, "discord_id": discord_id}
        if key in ("signed", "declined"):
            EventSignup.objects.create(
                event=event,
                user=user,
                status=SignupStatus.APPROVED
                if key == "signed"
                else SignupStatus.CANCELLED,
            )
        if key == "messaged":
            PromoSend.objects.create(
                organization=org,
                event=event,
                recipient=user,
                sender_id=OF_PROMOTER.pk,
                text="Seeded audience invite",
                earns_points=False,
            )
    sender = CustomUser.objects.get(pk=OF_PROMOTER.pk)
    signup = EventSignup.objects.create(event=activity, user=sender)
    EventSignup.objects.filter(pk=signup.pk).update(signed_up_at=now)
    members.append(
        {
            "user": {"id": sender.discordId, "username": sender.username, "bot": False},
            "joined_at": now.isoformat(),
        }
    )
    cache.set(f"discord_members_{GUILD_ID}", members, timeout=3600)
    invalidate_obj(org)
    return refs
