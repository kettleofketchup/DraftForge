from django.contrib import admin
from django.urls import include, path
from rest_framework import routers

from app import views as app_views
from app.views import (
    DraftCreateView,
    DraftRoundCreateView,
    GameCreateView,
    TeamCreateView,
    TeamView,
    DraftView,
    DraftRoundView,
    TournamentCreateView,
    TournamentView,
    UserCreateView,
    UserView,
    current_user,
    get_discord_members,
    get_discord_voice_channel_activity,
    get_user_guilds,
)

router = routers.DefaultRouter()
router.register(r"users", UserView, "users")
router.register(r"tournaments", TournamentView, "tournaments")
router.register(r"teams", TeamView, "teams")
router.register(
    r"drafts",
    DraftView,
    "drafts",
)
router.register(
    r"draftrounds",
    DraftRoundView,
    "draftrounds",
)

from django.views.generic.base import RedirectView

urlpatterns = [
    path("done/", RedirectView.as_view(url="http://localhost:5173")),
    path("", app_views.home),
    path("admin/", admin.site.urls),
    path("email-sent/", app_views.validation_sent),
    path("login/", app_views.home),
    path("logout/", app_views.logout),
    # path("done/", app_views.done, name="done"),
    path("ajax-auth/<backend>/", app_views.ajax_auth, name="ajax-auth"),
    path("email/", app_views.require_email, name="require_email"),
    path("country/", app_views.require_country, name="require_country"),
    path("city/", app_views.require_city, name="require_city"),
    path("", include("social_django.urls")),
    path("api/", include(router.urls)),
    path("api/current_user", current_user),
    path("api/user/register", UserCreateView.as_view()),
    path("api/tournament/register", TournamentCreateView.as_view()),
    path("api/team/register", TeamCreateView.as_view()),
    path("api/game/register", GameCreateView.as_view()),
    path("api/dtx_members", get_discord_members, name="dtx_members"),
    path("api/discord-members/", get_discord_members, name="discord-members"),
    path("api/discord-user-guilds/", get_user_guilds, name="discord-user-guilds"),
    path("api/logout", app_views.logout),
    path(
        "api/discord-voice-activity/",
        get_discord_voice_channel_activity,
        name="discord-voice-activity",
    ),
    path("api/draft/register", DraftCreateView.as_view()),
    path("api/draftround/register", DraftRoundCreateView.as_view()),
]
