from social_core.pipeline.partial import partial

from .models import CustomUser, DiscordInfo


def save_discord(
    strategy, details, user: CustomUser = None, is_new=False, *args, **kwargs
):
    social_auth = user.social_auth.get()
    discordId = social_auth.extra_data["id"]
    avatar = social_auth.extra_data["avatar"]
    discordUsername = social_auth.extra_data["avatar"]
    user.avatar = avatar
    user.discordId = discordId
    user.discordUsername = discordUsername
    user.save()
    return None
