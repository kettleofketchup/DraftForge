# Re-export all views from views_main.py
# This allows imports like `from app.views import UserView` to work

from app.views_main import (  # ViewSets; Create views; Functions
    DraftCreateView,
    DraftRoundCreateView,
    DraftRoundView,
    DraftView,
    GameCreateView,
    GameView,
    TeamCreateView,
    TeamView,
    TournamentCreateView,
    TournamentListView,
    TournamentsBasicView,
    TournamentView,
    UserCreateView,
    UserView,
    ajax_auth,
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

# Also import bracket functions
from .bracket import advance_winner, generate_bracket, get_bracket, save_bracket

__all__ = [
    # ViewSets
    "UserView",
    "TournamentView",
    "TournamentListView",
    "TeamView",
    "DraftView",
    "DraftRoundView",
    "GameView",
    "TournamentsBasicView",
    # Create views
    "UserCreateView",
    "GameCreateView",
    "TeamCreateView",
    "TournamentCreateView",
    "DraftCreateView",
    "DraftRoundCreateView",
    # Functions
    "logout",
    "home",
    "home_stats",
    "done",
    "validation_sent",
    "require_email",
    "require_country",
    "require_city",
    "ajax_auth",
    "current_user",
    "refresh_avatar",
    "refresh_user_avatar_admin",
    "refresh_all_avatars",
    # Bracket functions
    "get_bracket",
    "generate_bracket",
    "save_bracket",
    "advance_winner",
]
