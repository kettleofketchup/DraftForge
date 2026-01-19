from django.contrib.auth import get_user_model
from social_core.pipeline.partial import partial

from .models import CustomUser, PositionsModel

User = get_user_model()
import logging

# Get an instance of a logger
logger = logging.getLogger(__name__)


def save_discord(
    strategy, details, user: CustomUser = None, is_new=False, *args, **kwargs
):
    social_auth = user.social_auth.get()
    discordId = social_auth.extra_data["id"]
    avatar = social_auth.extra_data["avatar"]
    logger.info(f"SAVE_DISCORD {social_auth.extra_data}")
    discordUsername = social_auth.extra_data["username"]

    # Only create positions if user doesn't have any (preserve existing positions!)
    if not user.positions_id:
        position = PositionsModel.objects.create()
        user.positions = position

    user.avatar = avatar
    user.discordId = discordId
    user.discordUsername = discordUsername
    user.username = discordUsername
    user.save()
    return None


def associate_by_discord_id(
    backend, details, social, user=None, is_new=False, *args, **kwargs
):
    """
    Connect to a user if their discord ID matches an existing user.
    `id` is the Discord ID from the provider.
    """

    if user:
        logger.warning(f"user already exists: {details}")

        logger.warning(f"user already exists: {user}")
        return None  # Already authenticated or linked

    discordId = details.get("id")
    logger.warning(f"discordID: {discordId}")

    if not discordId:
        return None
    try:
        existing_user = User.objects.get(discordId=discordId).first()
        logger.warning(f"Found existing user: {existing_user}")
        return {"user": existing_user}
    except User.DoesNotExist:
        return None


def associate_by_discord_username(backend, details, user=None, *args, **kwargs):
    """
    Connect to a user if their discord username matches an existing user.
    `username` is the Discord username from the provider.
    """
    if user:
        return None  # Already authenticated or linked

    discordUsername = details.get("username")
    logger.warning(f"discordUsername: {discordUsername}")
    if not discordUsername:
        return None

    try:
        existing_user = User.objects.get(username=discordUsername)
        logger.warning(f"Found existing user: {existing_user}")
        return {"user": existing_user}
    except User.DoesNotExist:
        pass

    try:
        existing_user = User.objects.get(discordUsername=discordUsername)
        logger.warning(f"Found existing user: {existing_user}")
        return {"user": existing_user}
    except User.DoesNotExist:
        return None
