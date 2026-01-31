import logging
from venv import create

from django.contrib import admin
from django.urls import include, path
from rest_framework import routers

log = logging.getLogger(__name__)

from django.views.generic.base import RedirectView

from app import views_main as app_views
from app.functions.herodraft_views import (
    abandon_draft,
    create_herodraft,
    do_submit_choice,
    do_submit_pick,
    do_trigger_roll,
    get_herodraft,
    list_available_heroes,
    list_events,
    pause_draft,
    reset_draft,
    resume_draft,
    set_ready,
)
from app.functions.tournament import (
    create_team_from_captain,
    generate_draft_rounds,
    get_draft_style_mmrs,
    pick_player_for_round,
    rebuild_team,
    undo_last_pick,
)
from app.functions.user import profile_update
from app.views import (
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
    current_user,
)
from app.views.admin_team import (
    add_league_admin,
    add_league_staff,
    add_org_admin,
    add_org_staff,
    remove_league_admin,
    remove_league_staff,
    remove_org_admin,
    remove_org_staff,
    search_users,
    transfer_org_ownership,
)
from app.views_joke import buy_tango, get_tangoes
from common.utils import isTestEnvironment

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
router.register(r"games", GameView, "games")

router.register(r"organizations", app_views.OrganizationView, basename="organization")
router.register(r"leagues", app_views.LeagueView, basename="league")

router.register(r"tournaments-basic", TournamentsBasicView, "tournaments-basic")
router.register(r"tournaments-list", TournamentListView, "tournaments-list")
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
    # User search (must be before router to avoid conflict with UserView)
    path("api/users/search/", search_users, name="search_users"),
    path("api/", include(router.urls)),
    path("api/current_user", current_user),
    path("api/home-stats/", app_views.home_stats, name="home_stats"),
    path("api/user/register", UserCreateView.as_view()),
    path("api/tournament/register", TournamentCreateView.as_view()),
    path("api/team/register", TeamCreateView.as_view()),
    path("api/game/register", GameCreateView.as_view()),
    path("api/logout", app_views.logout),
    path("api/draft/get-style-mmrs", get_draft_style_mmrs, name="get-draft-style-mmrs"),
    path("api/draft/register", DraftCreateView.as_view()),
    path("api/draftround/register", DraftRoundCreateView.as_view()),
    path(
        "api/tournaments/create-team-from-captain",
        create_team_from_captain,
        name="create-team-from-captain",
    ),
    path(
        "api/tournaments/init-draft",
        generate_draft_rounds,
        name="init-draft",
    ),
    path(
        "api/tournaments/draft-rebuild",
        rebuild_team,
        name="draft-rebuild",
    ),
    path(
        "api/tournaments/pick_player",
        pick_player_for_round,
        name="pick_player",
    ),
    path(
        "api/tournaments/undo-pick",
        undo_last_pick,
        name="undo-pick",
    ),
    path("api/avatars/refresh/", app_views.refresh_all_avatars, name="refresh-avatars"),
    path("api/profile_update", profile_update, name="profile_update"),
    path("api/jokes/tangoes/", get_tangoes, name="get-tangoes"),
    path("api/jokes/tangoes/buy/", buy_tango, name="buy-tango"),
    path("api/steam/", include("steam.urls")),
    path("api/bracket/", include("bracket.urls")),
    path("api/discord/", include("discordbot.urls")),
    # HeroDraft (Captain's Mode) endpoints
    path(
        "api/games/<int:game_pk>/create-herodraft/",
        create_herodraft,
        name="create_herodraft",
    ),
    path("api/herodraft/<int:draft_pk>/", get_herodraft, name="get_herodraft"),
    path(
        "api/herodraft/<int:draft_pk>/set-ready/", set_ready, name="herodraft_set_ready"
    ),
    path(
        "api/herodraft/<int:draft_pk>/trigger-roll/",
        do_trigger_roll,
        name="herodraft_trigger_roll",
    ),
    path(
        "api/herodraft/<int:draft_pk>/submit-choice/",
        do_submit_choice,
        name="herodraft_submit_choice",
    ),
    path(
        "api/herodraft/<int:draft_pk>/submit-pick/",
        do_submit_pick,
        name="herodraft_submit_pick",
    ),
    path(
        "api/herodraft/<int:draft_pk>/list-events/",
        list_events,
        name="herodraft_list_events",
    ),
    path(
        "api/herodraft/<int:draft_pk>/list-available-heroes/",
        list_available_heroes,
        name="herodraft_list_available_heroes",
    ),
    path(
        "api/herodraft/<int:draft_pk>/abandon/",
        abandon_draft,
        name="herodraft_abandon",
    ),
    path(
        "api/herodraft/<int:draft_pk>/reset/",
        reset_draft,
        name="herodraft_reset",
    ),
    path(
        "api/herodraft/<int:draft_pk>/pause/",
        pause_draft,
        name="herodraft_pause",
    ),
    path(
        "api/herodraft/<int:draft_pk>/resume/",
        resume_draft,
        name="herodraft_resume",
    ),
    # Admin Team Management - Organization
    path(
        "api/organizations/<int:org_id>/admins/",
        add_org_admin,
        name="add_org_admin",
    ),
    path(
        "api/organizations/<int:org_id>/admins/<int:user_id>/",
        remove_org_admin,
        name="remove_org_admin",
    ),
    path(
        "api/organizations/<int:org_id>/staff/",
        add_org_staff,
        name="add_org_staff",
    ),
    path(
        "api/organizations/<int:org_id>/staff/<int:user_id>/",
        remove_org_staff,
        name="remove_org_staff",
    ),
    path(
        "api/organizations/<int:org_id>/transfer-ownership/",
        transfer_org_ownership,
        name="transfer_org_ownership",
    ),
    # League admin team
    path(
        "api/leagues/<int:league_id>/admins/",
        add_league_admin,
        name="add_league_admin",
    ),
    path(
        "api/leagues/<int:league_id>/admins/<int:user_id>/",
        remove_league_admin,
        name="remove_league_admin",
    ),
    path(
        "api/leagues/<int:league_id>/staff/",
        add_league_staff,
        name="add_league_staff",
    ),
    path(
        "api/leagues/<int:league_id>/staff/<int:user_id>/",
        remove_league_staff,
        name="remove_league_staff",
    ),
]

log.warning(f"Test Environ:  {isTestEnvironment()}")
if isTestEnvironment():
    log.warning("Adding test environment URLs")
    urlpatterns += [
        path("api/tests/", include("tests.urls")),
    ]
