from django.urls import path

from . import views
from .functions import api as steam_api
from .views import LeaderboardView, LeagueStatsView, MyLeagueStatsView

urlpatterns = [
    # Match endpoints
    path("match/<int:match_id>/", views.MatchDetailView.as_view(), name="match_detail"),
    path(
        "matches/<int:match_id>/",
        views.MatchRetrieveView.as_view(),
        name="match-detail",
    ),
    # Sync operations (Staff only)
    path("sync/", steam_api.sync_league, name="steam_sync"),
    path("retry-failed/", steam_api.retry_failed, name="steam_retry_failed"),
    path("relink-users/", steam_api.relink_users, name="steam_relink_users"),
    # Query endpoints (Public)
    path("find-by-players/", steam_api.find_by_players, name="steam_find_by_players"),
    path("live/", steam_api.get_live_games, name="steam_live_games"),
    path("sync-status/", steam_api.get_sync_status, name="steam_sync_status"),
    # Game-Match Auto-Linking
    path("auto-link/", steam_api.auto_link_tournament, name="steam_auto_link"),
    path("auto-assign/", steam_api.auto_assign_matches, name="steam_auto_assign"),
    path(
        "suggestions/tournament/<int:tournament_id>/",
        steam_api.get_tournament_suggestions,
        name="steam_tournament_suggestions",
    ),
    path(
        "suggestions/game/<int:game_id>/",
        steam_api.get_game_suggestions,
        name="steam_game_suggestions",
    ),
    path(
        "suggestions/<int:suggestion_id>/confirm/",
        steam_api.confirm_match_suggestion,
        name="steam_confirm_suggestion",
    ),
    path(
        "suggestions/<int:suggestion_id>/dismiss/",
        steam_api.dismiss_match_suggestion,
        name="steam_dismiss_suggestion",
    ),
    # Leaderboard and League Stats endpoints
    path("leaderboard/", LeaderboardView.as_view(), name="leaderboard"),
    path("league-stats/me/", MyLeagueStatsView.as_view(), name="my-league-stats"),
    path("league-stats/<int:user_id>/", LeagueStatsView.as_view(), name="league-stats"),
    # Game Match Linking
    path(
        "games/<int:game_id>/match-suggestions/",
        steam_api.get_game_match_suggestions,
        name="game_match_suggestions",
    ),
    path(
        "games/<int:game_id>/link-match/",
        steam_api.link_game_match,
        name="link_game_match",
    ),
    path(
        "games/<int:game_id>/unlink-match/",
        steam_api.unlink_game_match,
        name="unlink_game_match",
    ),
]
