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
    events        event state, event reads, repeaters, due scheduled events,
                  nightly sign-up records purge
    steam         league sync state, matches, league stats, MMR
    ops_notices   emit/resolve operations notices
    mmr_requests  nightly MMR screenshot retention purge

The tournament client (tournament/game reads, hero-draft creation) lives in
``tournament.internal_client`` on the same transport. User avatar and Discord-name
clients live in ``user.internal_client``.

Call sites use the re-exports below (``internal_client.get_event(...)``). Tests that
stub HTTP patch ``app.internal_client.transport.post`` (or ``get``/``patch``); tests
that stub a client function patch it here and, for calls made inside its own module,
on that module too.
"""

from app.internal_client import transport
from app.internal_client.discord import (
    begin_signup_delivery,
    check_message_log_exists,
    claim_discord_message_log,
    claim_discord_message_log_result,
    clear_event_signup_state,
    complete_signup_delivery,
    create_activity_notification_invite,
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
    get_signup_blocked_event_ids,
    get_sync_discord_state,
    mark_signup_delivery_sending,
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
    purge_signup_records,
    transition_event_state,
)
from app.internal_client.mmr_requests import purge_mmr_screenshots
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
from app.internal_client.transport import InternalAPIUnavailable

__all__ = [
    "InternalAPIUnavailable",
    "OpsNoticeTransientError",
    "auto_close_event",
    "batch_upsert_matches",
    "begin_signup_delivery",
    "check_message_log_exists",
    "claim_discord_message_log",
    "claim_discord_message_log_result",
    "create_activity_notification_invite",
    "clear_event_signup_state",
    "complete_signup_delivery",
    "create_event_dm",
    "create_event_log",
    "create_message_log",
    "create_or_update_announcement",
    "create_or_update_signup_message",
    "create_tournament_log",
    "emit_ops_notice",
    "finalize_discord_message_log",
    "generate_repeater_events",
    "get_active_repeaters",
    "get_discord_event_state",
    "get_due_scheduled_events",
    "get_event",
    "get_event_for_task",
    "get_event_signups",
    "get_events",
    "get_events_list",
    "get_fired_message_sources",
    "get_first_message_log",
    "get_or_create_discord_event",
    "get_repeater_subscribers",
    "get_signup_blocked_event_ids",
    "get_steam_sync_state",
    "get_sync_discord_state",
    "get_tracked_steam_league_ids",
    "mark_signup_delivery_sending",
    "purge_mmr_screenshots",
    "purge_signup_records",
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
]
