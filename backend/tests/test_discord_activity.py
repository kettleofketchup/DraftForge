"""Test endpoint that stages a Discord Activity launch (TEST ONLY)."""

import secrets

from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from app.models import CustomUser, Game, Tournament
from common.utils import isTestEnvironment
from discordbot.activity_fake import fake_code, register_instance
from discordbot.activity_intent import intent_key
from discordbot.models import DraftActivityChannel, DraftActivityInstance
from discordbot.utils import redis_client
from draft.models import DraftTeam, HeroDraft
from telemetry.logging import get_logger
from tests.data.tournaments import ACTIVITY_BRACKET_CONFIG
from tests.data.users import ADMIN_USER
from tests.test_herodraft import _setup_draft_state

log = get_logger(__name__)

ACTIVITY_GUILD_ID = "900000000000000007"
ACTIVITY_CHANNEL_ID = "900000000000000070"


def _draft_game(tournament: Tournament) -> Game | None:
    return (
        Game.objects.nocache()
        .select_related("radiant_team__captain", "dire_team__captain")
        .filter(
            tournament=tournament,
            status="pending",
            radiant_team__captain__isnull=False,
            dire_team__captain__isnull=False,
        )
        .order_by("-round", "bracket_type", "position")
        .first()
    )


def _hero_draft(game: Game) -> HeroDraft:
    draft = HeroDraft.objects.nocache().filter(game=game).first()
    if draft is None:
        draft = HeroDraft.objects.create(game=game, state="waiting_for_captains")
        DraftTeam.objects.create(draft=draft, tournament_team=game.radiant_team)
        DraftTeam.objects.create(draft=draft, tournament_team=game.dire_team)
    _setup_draft_state(draft, "waiting_for_captains")
    return draft


def _activity_user(game: Game) -> CustomUser | None:
    captain = game.radiant_team.captain if game.radiant_team else None
    if captain is not None and captain.discordId:
        return captain
    return (
        CustomUser.objects.nocache()
        .filter(pk=ADMIN_USER.pk, discordId__isnull=False)
        .exclude(discordId="")
        .first()
    )


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def discord_activity_setup(request: Request) -> Response:
    """Bind a voice channel to a hero draft in "Activity Bracket Test" and fake its instance."""
    if not isTestEnvironment(request):
        return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)
    tournament = (
        Tournament.objects.nocache().filter(name=ACTIVITY_BRACKET_CONFIG.name).first()
    )
    if tournament is None:
        return Response(
            {"error": f"'{ACTIVITY_BRACKET_CONFIG.name}' not found. Run populate."},
            status=status.HTTP_404_NOT_FOUND,
        )
    game = _draft_game(tournament)
    if game is None:
        return Response(
            {"error": "No pending bracket game with two captained teams."},
            status=status.HTTP_404_NOT_FOUND,
        )
    user = _activity_user(game)
    if user is None:
        return Response(
            {"error": "No Discord-linked user for the Activity."},
            status=status.HTTP_404_NOT_FOUND,
        )
    draft = _hero_draft(game)
    DraftActivityChannel.objects.update_or_create(
        channel_id=ACTIVITY_CHANNEL_ID,
        defaults={"guild_id": ACTIVITY_GUILD_ID, "draft": draft, "team_draft": None},
    )
    DraftActivityInstance.objects.filter(
        guild_id=ACTIVITY_GUILD_ID, channel_id=ACTIVITY_CHANNEL_ID
    ).delete()
    discord_id = str(user.discordId)
    redis_client.delete(intent_key(discord_id))
    instance_id = f"e2e-{secrets.token_hex(8)}"
    register_instance(instance_id, ACTIVITY_GUILD_ID, ACTIVITY_CHANNEL_ID, [discord_id])
    log.info(
        "test_discord_activity_setup",
        system="discord",
        subsystem="activity",
        tournament_id=tournament.pk,
        draft_id=draft.pk,
        user_id=user.pk,
        instance_id=instance_id,
    )
    return Response(
        {
            "instance_id": instance_id,
            "guild_id": ACTIVITY_GUILD_ID,
            "channel_id": ACTIVITY_CHANNEL_ID,
            "code": fake_code(discord_id),
            "discord_id": discord_id,
            "user_id": user.pk,
            "tournament_id": tournament.pk,
            "herodraft_id": draft.pk,
        }
    )
