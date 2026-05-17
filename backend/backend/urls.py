import logging

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
    add_league_member,
    add_league_staff,
    add_org_admin,
    add_org_member,
    add_org_staff,
    add_tournament_member,
    remove_league_admin,
    remove_league_staff,
    remove_org_admin,
    remove_org_staff,
    search_users,
    transfer_org_ownership,
    update_org_user,
)
from app.views.csv_import import import_csv_org, import_csv_tournament
from app.views.ssr import (
    EventSSRView,
    HeroDraftSSRView,
    LeagueSSRView,
    OrganizationSSRView,
    TournamentSSRView,
    UserSSRView,
)
from app.views_joke import buy_tango, get_tangoes
from common.utils import isTestEnvironment
from org.views import ClaimRequestViewSet
from org.views_profiles import (
    delete_user_dota_profile,
    get_my_dota_profile,
    get_user_dota_profile,
    update_my_dota_profile,
    update_user_dota_profile,
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
router.register(r"games", GameView, "games")

router.register(r"organizations", app_views.OrganizationView, basename="organization")
router.register(r"leagues", app_views.LeagueView, basename="league")
router.register(r"claim-requests", ClaimRequestViewSet, basename="claim-request")

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
    path("api/users/bulk/", app_views.bulk_users, name="bulk_users"),
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
    path("api/events/", include("events.urls")),
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
    # CSV Import
    path(
        "api/organizations/<int:org_id>/import-csv/",
        import_csv_org,
        name="import_csv_org",
    ),
    path(
        "api/tournaments/<int:tournament_id>/import-csv/",
        import_csv_tournament,
        name="import_csv_tournament",
    ),
    # Org user update
    path(
        "api/organizations/<int:org_id>/users/<int:org_user_id>/",
        update_org_user,
        name="update_org_user",
    ),
    # Dota profiles (self + staff)
    path(
        "api/organizations/<int:org_id>/my-dota-profile/",
        get_my_dota_profile,
        name="my-dota-profile",
    ),
    path(
        "api/organizations/<int:org_id>/my-dota-profile/update/",
        update_my_dota_profile,
        name="update-my-dota-profile",
    ),
    path(
        "api/organizations/<int:org_id>/users/<int:user_pk>/dota-profile/",
        get_user_dota_profile,
        name="user-dota-profile",
    ),
    path(
        "api/organizations/<int:org_id>/users/<int:user_pk>/dota-profile/update/",
        update_user_dota_profile,
        name="update-user-dota-profile",
    ),
    path(
        "api/organizations/<int:org_id>/users/<int:user_pk>/dota-profile/delete/",
        delete_user_dota_profile,
        name="delete-user-dota-profile",
    ),
    # Member management
    path(
        "api/organizations/<int:org_id>/members/",
        add_org_member,
        name="add_org_member",
    ),
    path(
        "api/leagues/<int:league_id>/members/",
        add_league_member,
        name="add_league_member",
    ),
    path(
        "api/tournaments/<int:tournament_id>/members/",
        add_tournament_member,
        name="add_tournament_member",
    ),
    # SSR endpoints — lightweight public data for meta tags and skeletons
    path(
        "api/tournaments/<int:pk>/ssr/",
        TournamentSSRView.as_view(),
        name="tournament_ssr",
    ),
    path(
        "api/organizations/<int:pk>/ssr/",
        OrganizationSSRView.as_view(),
        name="organization_ssr",
    ),
    path("api/leagues/<int:pk>/ssr/", LeagueSSRView.as_view(), name="league_ssr"),
    path("api/events/<int:pk>/ssr/", EventSSRView.as_view(), name="event_ssr"),
    path(
        "api/herodraft/<int:pk>/ssr/", HeroDraftSSRView.as_view(), name="herodraft_ssr"
    ),
    path("api/users/<int:pk>/ssr/", UserSSRView.as_view(), name="user_ssr"),
]

# Event task schedule
from events.views import fire_event_task, get_event_task_schedule

urlpatterns += [
    path(
        "api/events/<int:event_id>/task-schedule/",
        get_event_task_schedule,
        name="event_task_schedule",
    ),
    path(
        "api/events/<int:event_id>/task-schedule/<str:task_name>/fire/",
        fire_event_task,
        name="fire_event_task",
    ),
]

# Internal API — celery workers and Discord bot (token auth via X-Internal-Token)
from app.views.internal import (
    check_message_log_exists,
    claim_discord_message_log,
    clear_event_signup_state,
    create_discord_event_log,
    create_discord_message_log,
    finalize_discord_message_log,
    create_event_dm,
    create_herodraft_for_game,
    create_or_update_announcement,
    create_or_update_signup_message,
    create_tournament_log,
    generate_repeater_events,
    get_active_repeaters,
    get_discord_event_state,
    get_due_scheduled_events,
    get_event_for_task,
    get_games_without_herodraft,
    get_match_participants,
    get_or_create_discord_event,
    get_repeater_subscribers,
    get_sync_discord_state,
    get_tournament_for_task,
    get_tournament_participants,
    list_users_for_avatar_check,
    search_message_logs,
    transition_event_state,
    update_discord_event,
    update_event_dm,
    update_scheduled_event,
    update_tournament_log,
    update_user_avatar,
)

urlpatterns += [
    path("api/internal/discord/message-log/", create_discord_message_log),
    path("api/internal/discord/message-log/claim/", claim_discord_message_log),
    path(
        "api/internal/discord/message-log/<int:log_id>/finalize/",
        finalize_discord_message_log,
    ),
    path("api/internal/discord/event-log/", create_discord_event_log),
    path("api/internal/discord/tournament-log/", create_tournament_log),
    path("api/internal/discord/tournament-log/<int:pk>/", update_tournament_log),
    path("api/internal/discord/events/get-or-create/", get_or_create_discord_event),
    path("api/internal/discord/events/<int:pk>/", update_discord_event),
    path("api/internal/discord/signup-message/", create_or_update_signup_message),
    path(
        "api/internal/discord/signup-message/clear/",
        clear_event_signup_state,
    ),
    path("api/internal/discord/announcement/", create_or_update_announcement),
    path("api/internal/discord/event-dm/", create_event_dm),
    path("api/internal/discord/event-dm/<int:pk>/", update_event_dm),
    path("api/internal/discord/scheduled-events/<int:pk>/", update_scheduled_event),
    path("api/internal/events/<int:pk>/transition/", transition_event_state),
    path("api/internal/discord/check-log/", check_message_log_exists),
    path("api/internal/discord/message-logs/", search_message_logs),
    path("api/internal/discord/event-state/<int:event_id>/", get_discord_event_state),
    path("api/internal/discord/sync-state/", get_sync_discord_state),
    path(
        "api/internal/repeaters/<int:repeater_id>/subscribers/",
        get_repeater_subscribers,
    ),
    path(
        "api/internal/repeaters/active/",
        get_active_repeaters,
        name="internal_active_repeaters",
    ),
    path(
        "api/internal/repeaters/<int:repeater_id>/generate/",
        generate_repeater_events,
        name="internal_generate_repeater_events",
    ),
    path("api/internal/scheduled-events/due/", get_due_scheduled_events),
    path("api/internal/events/<int:event_id>/full/", get_event_for_task),
    # Tournament endpoints
    path(
        "api/internal/tournaments/<int:tournament_id>/full/",
        get_tournament_for_task,
    ),
    path(
        "api/internal/tournaments/<int:tournament_id>/participants/",
        get_tournament_participants,
    ),
    path(
        "api/internal/tournaments/<int:tournament_id>/games-without-herodraft/",
        get_games_without_herodraft,
    ),
    path(
        "api/internal/games/<int:game_id>/participants/",
        get_match_participants,
    ),
    path(
        "api/internal/games/<int:game_id>/create-herodraft/",
        create_herodraft_for_game,
    ),
    # User avatar management
    path("api/internal/users/avatar-check/", list_users_for_avatar_check),
    path("api/internal/users/<int:pk>/avatar/", update_user_avatar),
]

# Internal API — Steam sync endpoints
from steam.views_internal import (
    recalculate_mmr,
    steam_sync_state,
    store_match,
    update_league_stats,
)

urlpatterns += [
    path("api/internal/steam/sync-state/<int:league_id>/", steam_sync_state),
    path("api/internal/steam/store-match/", store_match),
    path(
        "api/internal/steam/update-league-stats/<int:league_id>/", update_league_stats
    ),
    path("api/internal/steam/recalculate-mmr/<int:user_id>/", recalculate_mmr),
]

log.debug(f"Test Environ:  {isTestEnvironment()}")
if isTestEnvironment():
    log.debug("Adding test environment URLs")
    urlpatterns += [
        path("api/tests/", include("tests.urls")),
    ]
