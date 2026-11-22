from django.contrib import admin
from django.urls import include, path
from django.views.generic.base import RedirectView
from rest_framework import routers

from app import views_main as app_views
from app.functions.tournament import create_team_from_captain
from app.functions.user import profile_update
from app.views import (
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
from app.views.admin_team import add_tournament_member, search_users
from app.views.csv_import import import_csv_org, import_csv_tournament
from app.views.internal import (
    auto_close_event,
    check_message_log_exists,
    claim_discord_message_log,
    clear_event_signup_state,
    create_discord_event_log,
    create_discord_message_log,
    create_event_dm,
    create_or_update_announcement,
    create_or_update_signup_message,
    create_tournament_log,
    finalize_discord_message_log,
    generate_repeater_events,
    get_active_repeaters,
    get_discord_event_state,
    get_due_scheduled_events,
    get_event_for_task,
    get_match_participants,
    get_or_create_discord_event,
    get_repeater_subscribers,
    get_sync_discord_state,
    get_tournament_for_task,
    get_tournament_participants,
    list_users_for_avatar_check,
    search_message_logs,
    sweep_stale_discord_leases,
    transition_event_state,
    update_discord_event,
    update_event_dm,
    update_scheduled_event,
    update_tournament_log,
    update_user_avatar,
)
from app.views.ssr import EventSSRView, TournamentSSRView, UserSSRView
from app.views.steam_verification import steam_verification
from app.views_joke import buy_tango, get_tangoes
from common.utils import isTestEnvironment
from draft.views.team_api import DraftRoundView, DraftView
from events.views import fire_event_task, get_event_task_schedule
from league.ssr import LeagueSSRView
from league.views import LeagueView
from league.views_admin_team import (
    add_league_admin,
    add_league_member,
    add_league_staff,
    remove_league_admin,
    remove_league_staff,
)
from org.ssr import OrganizationSSRView
from org.views import ClaimRequestViewSet
from org.views_admin_team import (
    add_org_admin,
    add_org_member,
    add_org_staff,
    remove_org_admin,
    remove_org_staff,
    transfer_org_ownership,
    update_org_user,
)
from org.views_features import org_features, org_promoters, remove_org_promoter
from org.views_organization import OrganizationView
from org.views_profiles import (
    delete_user_dota_profile,
    get_my_dota_profile,
    get_user_dota_profile,
    update_my_dota_profile,
    update_user_dota_profile,
)
from org.views_settings import org_settings_view
from steam.views_internal import (
    recalculate_mmr,
    steam_sync_state,
    store_match,
    tracked_leagues,
    update_league_stats,
)
from telemetry.logging import get_logger
from user.internal.avatar import (
    bulk_update_user_avatars,
    list_discord_guild_ids,
    list_discord_linked_users,
)
from user.internal.discord_names import (
    bulk_update_member_names,
    list_discord_name_sync_targets,
)

log = get_logger(__name__)

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

router.register(r"organizations", OrganizationView, basename="organization")
router.register(r"leagues", LeagueView, basename="league")
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
    path("email/", app_views.require_email, name="require_email"),
    path("country/", app_views.require_country, name="require_country"),
    path("city/", app_views.require_city, name="require_city"),
    path("", include("social_django.urls")),
    # User search (must be before router to avoid conflict with UserView)
    path("api/users/search/", search_users, name="search_users"),
    path("api/users/bulk/", app_views.bulk_users, name="bulk_users"),
    path(
        "api/users/steam-account-id/<int:steam_account_id>/",
        app_views.steam_account_id_lookup,
        name="steam_account_id_lookup",
    ),
    path(
        "api/users/<int:pk>/steam-verification/",
        steam_verification,
        name="user_steam_verification",
    ),
    # User profile (see backend/user/urls.py)
    path("api/users/", include("user.urls")),
    path("api/", include(router.urls)),
    path("api/current_user", current_user),
    path("api/home-stats/", app_views.home_stats, name="home_stats"),
    path("api/user/register", UserCreateView.as_view()),
    path("api/tournament/register", TournamentCreateView.as_view()),
    path("api/team/register", TeamCreateView.as_view()),
    path("api/game/register", GameCreateView.as_view()),
    path("api/logout", app_views.logout),
    path(
        "api/tournaments/create-team-from-captain",
        create_team_from_captain,
        name="create-team-from-captain",
    ),
    path("api/avatars/refresh/", app_views.refresh_all_avatars, name="refresh-avatars"),
    path("api/profile_update", profile_update, name="profile_update"),
    path("api/jokes/tangoes/", get_tangoes, name="get-tangoes"),
    path("api/jokes/tangoes/buy/", buy_tango, name="buy-tango"),
    path("api/steam/", include("steam.urls")),
    path("api/bracket/", include("bracket.urls")),
    path("api/discord/", include("discordbot.urls")),
    path("api/events/", include("events.urls")),
    # Hero and team draft endpoints
    path("", include("draft.urls")),
    # dota_lobby in-game lobby for a game (lobby app)
    path("api/games/<int:game_pk>/lobby/", include("lobby.urls")),
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
    path(
        "api/organizations/<int:org_id>/features/",
        org_features,
        name="org-features",
    ),
    path(
        "api/organizations/<int:org_id>/settings/",
        org_settings_view,
        name="org-settings",
    ),
    path(
        "api/organizations/<int:org_id>/promoters/",
        org_promoters,
        name="org-promoters",
    ),
    path(
        "api/organizations/<int:org_id>/promoters/<int:user_id>/",
        remove_org_promoter,
        name="org-promoter-remove",
    ),
    path(
        "api/organizations/<int:org_id>/contributions/",
        include("org.contributions.urls"),
    ),
    path(
        "api/organizations/<int:org_id>/standing/",
        include("org.standing.urls"),
    ),
    path(
        "api/organizations/<int:org_id>/conduct/",
        include("org.conduct.urls"),
    ),
    path(
        "api/organizations/<int:org_id>/promotion/",
        include("org.promotion.urls"),
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
    path("api/users/<int:pk>/ssr/", UserSSRView.as_view(), name="user_ssr"),
]

# Event task schedule
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
    path("api/internal/events/<int:pk>/auto-close/", auto_close_event),
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
    path("", include("draft.internal_urls")),
    path(
        "api/internal/tournaments/<int:tournament_id>/full/",
        get_tournament_for_task,
    ),
    path(
        "api/internal/tournaments/<int:tournament_id>/participants/",
        get_tournament_participants,
    ),
    path(
        "api/internal/games/<int:game_id>/participants/",
        get_match_participants,
    ),
    # User avatar management
    path("api/internal/users/avatar-check/", list_users_for_avatar_check),
    path("api/internal/users/<int:pk>/avatar/", update_user_avatar),
    # Batched avatar refresh (worker → backend via internal_client)
    path(
        "api/internal/users/discord-linked/",
        list_discord_linked_users,
        name="internal_list_discord_linked_users",
    ),
    path(
        "api/internal/orgs/discord-guild-ids/",
        list_discord_guild_ids,
        name="internal_list_discord_guild_ids",
    ),
    path(
        "api/internal/users/avatars/bulk-update/",
        bulk_update_user_avatars,
        name="internal_bulk_update_user_avatars",
    ),
    path(
        "api/internal/orgs/discord-name-sync-targets/",
        list_discord_name_sync_targets,
        name="internal_discord_name_sync_targets",
    ),
    path(
        "api/internal/discord/member-names/bulk-update/",
        bulk_update_member_names,
        name="internal_discord_member_names_bulk_update",
    ),
    # Discord lease sweeper (worker → backend via internal_client)
    path(
        "api/internal/discord/sweep-stale-leases/",
        sweep_stale_discord_leases,
        name="internal_sweep_stale_discord_leases",
    ),
]

# Internal API — Discord bot signup-flow callbacks (bot → backend HTTP wrappers)
urlpatterns += [
    path("api/internal/discord/", include("discordbot.internal_urls")),
]

# Internal API — dota_lobby lobbies: Celery task endpoints and the webhook receiver
urlpatterns += [
    path("api/internal/lobbies/", include("lobby.internal_urls")),
]

# Internal API — Steam sync endpoints
urlpatterns += [
    path("api/internal/steam/sync-state/<int:league_id>/", steam_sync_state),
    path("api/internal/steam/store-match/", store_match),
    path("api/internal/steam/tracked-leagues/", tracked_leagues),
    path(
        "api/internal/steam/update-league-stats/<int:league_id>/", update_league_stats
    ),
    path("api/internal/steam/recalculate-mmr/<int:user_id>/", recalculate_mmr),
]

log.debug(
    "test_environ_check", system="api", subsystem="routing", is_test=isTestEnvironment()
)
if isTestEnvironment():
    log.debug("test_urls_added", system="api", subsystem="routing")
    urlpatterns += [
        path("api/tests/", include("tests.urls")),
    ]

urlpatterns += [
    path("api/internal/ops-notices/", include("opsnotices.internal_urls")),
]

urlpatterns += [path("", include("opsnotices.urls"))]
