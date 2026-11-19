"""HTTP client for internal API calls from celery workers and Discord bot.

All external processes MUST use this client instead of importing Django models.
Django/Daphne is the sole DB reader/writer.

Config:
    INTERNAL_API_URL: defaults to http://backend:8000/api/internal (Docker).
                      Set to https://dota.kettle.sh/api/internal for remote.
    INTERNAL_SERVICE_TOKEN: shared secret for X-Internal-Token header.
    Both live on ``transport`` (override ``transport.INTERNAL_API_URL``, not a
    package attribute).

Modules:
    transport     URLs, auth headers, error logging, post/patch/get/api_get
    discord       message-log leases, audit logs, Discord events/messages, sync state
    events        event state, event reads, repeaters, due scheduled events
    steam         league sync state, matches, league stats, MMR
    users         avatars, batched avatar refresh, Discord name sync
    tournaments   tournament/game reads, hero-draft creation
    ops_notices   emit/resolve operations notices

Call sites use the re-exports below (``internal_client.get_event(...)``). Tests that
stub HTTP patch ``app.internal_client.transport.post`` (or ``get``/``patch``); tests
that stub a client function patch it here and, for calls made inside its own module,
on that module too.
"""

from app.internal_client import transport
from app.internal_client.transport import InternalAPIUnavailable
from app.internal_client.discord import (
    check_message_log_exists,
    claim_discord_message_log,
    clear_event_signup_state,
    create_event_dm,
    create_event_log,
    create_message_log,
    create_or_update_announcement,
    create_or_update_signup_message,
    create_tournament_log,
    finalize_discord_message_log,
    get_discord_event_state,
    get_fired_message_sources,
    get_first_message_log,
    get_or_create_discord_event,
    get_sync_discord_state,
    search_message_logs,
    sweep_discord_leases,
    update_discord_event,
    update_event_dm,
    update_scheduled_event,
    update_tournament_log,
)
from app.internal_client.events import (
    auto_close_event,
    generate_repeater_events,
    get_active_repeaters,
    get_due_scheduled_events,
    get_event,
    get_event_for_task,
    get_event_signups,
    get_events,
    get_events_list,
    get_repeater_subscribers,
    transition_event_state,
)
from app.internal_client.ops_notices import (
    OpsNoticeTransientError,
    emit_ops_notice,
    resolve_ops_notice,
)
from app.internal_client.steam import (
    batch_upsert_matches,
    get_steam_sync_state,
    get_tracked_steam_league_ids,
    recalculate_user_mmr,
    store_steam_match,
    update_league_stats,
    update_steam_sync_state,
    update_sync_state,
)
from app.internal_client.tournaments import (
    create_herodraft_for_game,
    get_auto_herodraft_games,
    get_match_participants,
    get_tournament_for_task,
    get_tournament_participants,
)
from app.internal_client.users import (
    bulk_update_member_names,
    bulk_update_user_avatars,
    get_users_for_avatar_check,
    list_discord_guild_ids,
    list_discord_linked_users,
    list_discord_name_sync_targets,
    update_user_avatar,
)

__all__ = [
    "InternalAPIUnavailable",
    "OpsNoticeTransientError",
    "auto_close_event",
    "batch_upsert_matches",
    "bulk_update_member_names",
    "bulk_update_user_avatars",
    "check_message_log_exists",
    "claim_discord_message_log",
    "clear_event_signup_state",
    "create_event_dm",
    "create_event_log",
    "create_herodraft_for_game",
    "create_message_log",
    "create_or_update_announcement",
    "create_or_update_signup_message",
    "create_tournament_log",
    "emit_ops_notice",
    "finalize_discord_message_log",
    "generate_repeater_events",
    "get_active_repeaters",
    "get_auto_herodraft_games",
    "get_discord_event_state",
    "get_due_scheduled_events",
    "get_event",
    "get_event_for_task",
    "get_event_signups",
    "get_events",
    "get_events_list",
    "get_fired_message_sources",
    "get_first_message_log",
    "get_match_participants",
    "get_or_create_discord_event",
    "get_repeater_subscribers",
    "get_steam_sync_state",
    "get_sync_discord_state",
    "get_tournament_for_task",
    "get_tournament_participants",
    "get_tracked_steam_league_ids",
    "get_users_for_avatar_check",
    "list_discord_guild_ids",
    "list_discord_linked_users",
    "list_discord_name_sync_targets",
    "recalculate_user_mmr",
    "resolve_ops_notice",
    "search_message_logs",
    "store_steam_match",
    "sweep_discord_leases",
    "transition_event_state",
    "transport",
    "update_discord_event",
    "update_event_dm",
    "update_league_stats",
    "update_scheduled_event",
    "update_steam_sync_state",
    "update_sync_state",
    "update_tournament_log",
    "update_user_avatar",
]
