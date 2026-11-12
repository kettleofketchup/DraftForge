import type {
  CaptainPresencePayload,
  CaptainReadyPayload,
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
  PlayerPickedPayload,
  RoundStartedPayload,
  TieRollPayload,
} from '~/types/draftEvent';

export function getEventMessage(event: DraftEvent): string {
  switch (event.event_type) {
    case 'draft_started':
      return 'Draft has started!';
    case 'draft_completed':
      return 'Draft completed!';
    case 'player_picked': {
      const p = event.payload as PlayerPickedPayload;
      return `${p.captain_name} picked ${p.picked_name} (Pick ${p.pick_number})`;
    }
    case 'tie_roll': {
      const p = event.payload as TieRollPayload;
      const lastRound = p.roll_rounds?.[p.roll_rounds.length - 1] ?? [];
      const rolls = lastRound.map((r) => r.roll).join(' vs ');
      return rolls ? `Tie resolved! ${p.winner_name} wins (${rolls})` : `Tie resolved! ${p.winner_name} wins`;
    }
    case 'captain_assigned': {
      const p = event.payload as { captain_name: string };
      return `${p.captain_name} is picking next`;
    }
    case 'pick_undone': {
      const p = event.payload as { undone_player_name: string; pick_number: number };
      return `Pick ${p.pick_number} undone (${p.undone_player_name})`;
    }
    case 'draft_lobby_opened': {
      const p = event.payload as DraftLobbyOpenedPayload;
      if (!p.timer_enabled) return 'Lobby opened — no pick clock';
      return `Lobby opened — ${p.grace_time_ms / 1000}s grace, ${p.reserve_time_ms / 1000}s reserve`;
    }
    case 'captain_ready':
      return `${(event.payload as CaptainReadyPayload).captain_name} is ready`;
    case 'captain_unready':
      return `${(event.payload as CaptainReadyPayload).captain_name} is not ready`;
    case 'captain_connected':
      return `${(event.payload as CaptainPresencePayload).captain_name} connected`;
    case 'captain_disconnected':
      return `${(event.payload as CaptainPresencePayload).captain_name} disconnected`;
    case 'draft_started_by_staff':
      return `Draft started by ${(event.payload as DraftStartedByStaffPayload).actor_name}`;
    case 'draft_force_started': {
      const p = event.payload as DraftForceStartedPayload;
      return `Draft force-started by ${p.actor_name} (${p.not_ready.length} not ready)`;
    }
    case 'round_started': {
      const p = event.payload as RoundStartedPayload;
      return `Pick #${p.pick_number}: ${p.captain_name} is on the clock`;
    }
    case 'draft_paused': {
      const p = event.payload as DraftPausedPayload;
      return p.reason === 'manual'
        ? `Draft paused by ${p.paused_by_name}`
        : `Draft paused — ${p.captain_name} disconnected`;
    }
    case 'draft_resumed':
      return 'Resuming draft…';
    case 'pick_timed_out': {
      const p = event.payload as PickTimedOutPayload;
      return `${p.captain_name} ran out of time on pick #${p.pick_number}`;
    }
    case 'pick_skipped': {
      const p = event.payload as PickSkippedPayload;
      const base = `${p.skipped_captain_name} ran out of time — ${p.next_captain_name} is up`;
      return p.deferred_to_pick_number === null
        ? base
        : `${base}, ${p.skipped_captain_name} picks at #${p.deferred_to_pick_number}`;
    }
    case 'pick_skip_unavailable': {
      const p = event.payload as PickSkipUnavailablePayload;
      return `${p.captain_name} ran out of time — waiting for ${p.captain_name} or staff to pick`;
    }
    case 'draft_options_changed': {
      const p = event.payload as DraftOptionsChangedPayload;
      const who = p.changed_by_name ?? 'Staff';
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

export function getEventToast(event: DraftEvent): string | null {
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
      return getEventMessage(event);
    case 'captain_disconnected':
      return (event.payload as CaptainPresencePayload).is_active_captain ? getEventMessage(event) : null;
    default:
      return null;
  }
}
