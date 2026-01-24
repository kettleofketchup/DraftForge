# Tasks package for background jobs
# Celery tasks are discovered automatically via autodiscover_tasks()

from app.tasks.avatar_refresh import (
    refresh_all_discord_data,
    refresh_discord_avatars,
    refresh_single_user_avatar,
)
