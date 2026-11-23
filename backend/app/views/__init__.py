# Re-export all views from views_main.py
# This allows imports like `from app.views import UserView` to work

from app.views_main import (  # ViewSets; Create views; Functions
    UserCreateView,
    UserView,
    bulk_users,
    current_user,
    done,
    home,
    home_stats,
    logout,
    refresh_all_avatars,
    refresh_avatar,
    refresh_user_avatar_admin,
    require_city,
    require_country,
    require_email,
    validation_sent,
)

__all__ = [
    # ViewSets
    "UserView",
    # Create views
    "UserCreateView",
    # Functions
    "bulk_users",
    "logout",
    "home",
    "home_stats",
    "done",
    "validation_sent",
    "require_email",
    "require_country",
    "require_city",
    "current_user",
    "refresh_avatar",
    "refresh_user_avatar_admin",
    "refresh_all_avatars",
]
