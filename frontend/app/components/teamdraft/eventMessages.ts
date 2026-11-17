import { displayNameById } from '~/lib/userDisplayName';
import type {
  CaptainAssignedPayload,
  CaptainPresencePayload,
  CaptainReadyPayload,
  CaptainRef,
  DraftEvent,
  DraftEventType,
  DraftForceStartedPayload,
  DraftLobbyOpenedPayload,
  DraftOptionsChangedPayload,
  DraftPausedPayload,
  DraftStartedByStaffPayload,
  PickSkippedPayload,
  PickSkipUnavailablePayload,
  PickTimedOutPayload,
  PickUndonePayload,
  PlayerPickedPayload,
  RoundStartedPayload,
  TieRollPayload,
} from '~/types/draftEvent';

export type NameResolver = (
  id: number | null | undefined,
  fallback: string | null | undefined,
) => string;

export const orgUserName =
  (orgId: number | null | undefined): NameResolver =>
  (id, fallback) =>
    displayNameById(id, fallback, orgId);

export const cachedUserName: NameResolver = orgUserName(null);

function captainName(p: CaptainRef, name: NameResolver): string {
  return name(p.captain_id, p.captain_name);
}

export function getEventMessage(
  event: DraftEvent,
  name: NameResolver = cachedUserName,
): string {
  switch (event.event_type) {
    case 'draft_started':
      return 'Draft has started!';
    case 'draft_completed':
      return 'Draft completed!';
    case 'player_picked': {
      const p = event.payload as PlayerPickedPayload;
      return `${name(p.captain_id, p.captain_name)} picked ${name(p.picked_id, p.picked_name)} (Pick ${p.pick_number})`;
    }
    case 'tie_roll': {
      const p = event.payload as TieRollPayload;
      const lastRound = p.roll_rounds?.[p.roll_rounds.length - 1] ?? [];
      const rolls = lastRound.map((r) => r.roll).join(' vs ');
      return rolls
        ? `Tie resolved! ${p.winner_name} wins (${rolls})`
        : `Tie resolved! ${p.winner_name} wins`;
    }
    case 'captain_assigned': {
      const p = event.payload as CaptainAssignedPayload;
      return `${name(p.captain_id, p.captain_name)} is picking next`;
    }
    case 'pick_undone': {
      const p = event.payload as PickUndonePayload;
      return `Pick ${p.pick_number} undone (${name(p.undone_player_id, p.undone_player_name)})`;
    }
    case 'draft_lobby_opened': {
      const p = event.payload as DraftLobbyOpenedPayload;
      if (!p.timer_enabled) return 'Lobby opened — no pick clock';
      return `Lobby opened — ${p.grace_time_ms / 1000}s grace, ${p.reserve_time_ms / 1000}s reserve`;
    }
    case 'captain_ready':
      return `${captainName(event.payload as CaptainReadyPayload, name)} is ready`;
    case 'captain_unready':
      return `${captainName(event.payload as CaptainReadyPayload, name)} is not ready`;
    case 'captain_connected':
      return `${captainName(event.payload as CaptainPresencePayload, name)} connected`;
    case 'captain_disconnected':
      return `${captainName(event.payload as CaptainPresencePayload, name)} disconnected`;
    case 'draft_started_by_staff': {
      const p = event.payload as DraftStartedByStaffPayload;
      return `Draft started by ${name(p.actor_id, p.actor_name)}`;
    }
    case 'draft_force_started': {
      const p = event.payload as DraftForceStartedPayload;
      return `Draft force-started by ${name(p.actor_id, p.actor_name)} (${p.not_ready.length} not ready)`;
    }
    case 'round_started': {
      const p = event.payload as RoundStartedPayload;
      return `Pick #${p.pick_number}: ${captainName(p, name)} is on the clock`;
    }
    case 'draft_paused': {
      const p = event.payload as DraftPausedPayload;
      return p.reason === 'manual'
        ? `Draft paused by ${name(p.paused_by_id, p.paused_by_name)}`
        : `Draft paused — ${captainName(p, name)} disconnected`;
    }
    case 'draft_resumed':
      return 'Resuming draft…';
    case 'pick_timed_out': {
      const p = event.payload as PickTimedOutPayload;
      return `${captainName(p, name)} ran out of time on pick #${p.pick_number}`;
    }
    case 'pick_skipped': {
      const p = event.payload as PickSkippedPayload;
      const skipped = name(p.skipped_captain_id, p.skipped_captain_name);
      const base = `${skipped} ran out of time — ${name(p.next_captain_id, p.next_captain_name)} is up`;
      return p.deferred_to_pick_number === null
        ? base
        : `${base}, ${skipped} picks at #${p.deferred_to_pick_number}`;
    }
    case 'pick_skip_unavailable': {
      const p = event.payload as PickSkipUnavailablePayload;
      const captain = captainName(p, name);
      return `${captain} ran out of time — waiting for ${captain} or staff to pick`;
    }
    case 'draft_options_changed': {
      const p = event.payload as DraftOptionsChangedPayload;
      const who = name(p.changed_by_id, p.changed_by_name ?? 'Staff');
      if (!p.timer_enabled) return `${who} turned the pick clock off`;
      return `${who} turned the pick clock on — ${p.grace_time_ms / 1000}s grace, ${p.reserve_time_ms / 1000}s reserve`;
    }
    default:
      return 'Draft event occurred';
  }
}

export function getEventIcon(eventType: DraftEventType): string {
  switch (eventType) {
    case 'draft_started':
      return '▶️';
    case 'draft_completed':
      return '🏁';
    case 'player_picked':
      return '🎯';
    case 'tie_roll':
      return '🎲';
    case 'captain_assigned':
      return '👑';
    case 'pick_undone':
      return '↩️';
    case 'draft_lobby_opened':
      return '🚪';
    case 'captain_ready':
      return '✅';
    case 'captain_unready':
      return '⏳';
    case 'captain_connected':
      return '🟢';
    case 'captain_disconnected':
      return '🔌';
    case 'draft_started_by_staff':
      return '🛠️';
    case 'draft_force_started':
      return '⚡';
    case 'round_started':
      return '⏱️';
    case 'draft_paused':
      return '⏸️';
    case 'draft_resumed':
      return '⏯️';
    case 'pick_timed_out':
      return '⌛';
    case 'pick_skipped':
      return '⏭️';
    case 'pick_skip_unavailable':
      return '🚧';
    case 'draft_options_changed':
      return '⚙️';
    default:
      return '📋';
  }
}

export function getEventToast(
  event: DraftEvent,
  name: NameResolver = cachedUserName,
): string | null {
  switch (event.event_type) {
    case 'draft_started':
    case 'draft_completed':
    case 'player_picked':
    case 'pick_skipped':
    case 'pick_skip_unavailable':
    case 'draft_paused':
    case 'draft_resumed':
    case 'draft_started_by_staff':
    case 'draft_force_started':
    case 'draft_options_changed':
      return getEventMessage(event, name);
    case 'captain_disconnected':
      return (event.payload as CaptainPresencePayload).is_active_captain
        ? getEventMessage(event, name)
        : null;
    default:
      return null;
  }
}
