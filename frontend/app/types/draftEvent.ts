import type { DraftOptions, TeamDraftState } from "~/components/teamdraft/schemas";

export type DraftEventType =
  | "draft_started"
  | "draft_completed"
  | "captain_assigned"
  | "player_picked"
  | "tie_roll"
  | "pick_undone"
  | "draft_lobby_opened"
  | "captain_ready"
  | "captain_unready"
  | "captain_connected"
  | "captain_disconnected"
  | "draft_started_by_staff"
  | "draft_force_started"
  | "round_started"
  | "draft_paused"
  | "draft_resumed"
  | "pick_timed_out"
  | "pick_skipped"
  | "pick_skip_unavailable";

export interface DraftEvent {
  pk: number;
  event_type: DraftEventType;
  payload: DraftEventPayload;
  actor: {
    pk: number;
    username: string;
    avatarUrl: string | null;
  } | null;
  created_at: string;
}

export type DraftEventPayload =
  | DraftStartedPayload
  | DraftCompletedPayload
  | CaptainAssignedPayload
  | PlayerPickedPayload
  | TieRollPayload
  | PickUndonePayload
  | CaptainPresencePayload
  | CaptainReadyPayload
  | DraftLobbyOpenedPayload
  | DraftStartedByStaffPayload
  | DraftForceStartedPayload
  | RoundStartedPayload
  | DraftPausedPayload
  | DraftResumedPayload
  | PickTimedOutPayload
  | PickSkippedPayload
  | PickSkipUnavailablePayload;

export interface DraftStartedPayload {
  draft_id: number;
  draft_style: string;
  team_count: number;
}

export interface DraftCompletedPayload {
  draft_id: number;
  draft_style: string;
  team_count: number;
}

export interface CaptainAssignedPayload {
  pick_number: number;
  captain_id: number;
  captain_name: string;
  captain_avatar_url?: string | null;
  team_id: number;
  was_tie: boolean;
  reason?: "timeout_skip";
}

export interface PlayerPickedPayload {
  pick_number: number;
  captain_id: number;
  captain_name: string;
  captain_avatar_url?: string | null;
  picked_id: number;
  picked_name: string;
  picked_avatar_url?: string | null;
  team_id: number | null;
  team_name: string | null;
}

export interface TieRollPayload {
  pick_number: number;
  tied_teams: {
    id: number;
    name: string;
    mmr: number;
  }[];
  roll_rounds: {
    team_id: number;
    roll: number;
  }[][];
  winner_id: number;
  winner_name: string;
}

export interface PickUndonePayload {
  pick_number: number;
  undone_player_id: number;
  undone_player_name: string;
  team_id: number | null;
  team_name: string | null;
}

export interface CaptainRef {
  captain_id: number;
  captain_name: string;
  captain_avatar_url?: string | null;
  team_id: number | null;
  team_name: string | null;
}

export interface CaptainPresencePayload extends CaptainRef {
  pick_number: number | null;
  is_active_captain: boolean;
}

export interface CaptainReadyPayload extends CaptainRef {
  pick_number: number | null;
}

export interface DraftLobbyOpenedPayload {
  timer_enabled: boolean;
  grace_time_ms: number;
  reserve_time_ms: number;
}

export interface DraftStartedByStaffPayload {
  actor_id: number;
  actor_name: string;
  pick_number: number | null;
}

export interface DraftForceStartedPayload extends DraftStartedByStaffPayload {
  not_ready: Array<{
    team_id: number;
    team_name: string;
    captain_id: number | null;
    captain_name: string | null;
  }>;
}

export interface RoundStartedPayload extends CaptainRef {
  pick_number: number;
  started_at: string;
  grace_time_ms: number;
  reserve_ms: number | null;
}

export interface DraftPausedPayload extends CaptainRef {
  reason: "manual" | "captain_disconnected";
  paused_by_id: number | null;
  paused_by_name: string | null;
  pick_number: number | null;
}

export interface DraftResumedPayload {
  resumed_by_id: number | null;
  resumed_by_name: string | null;
  resuming_until: string | null;
  pick_number: number | null;
}

export interface PickTimedOutPayload extends CaptainRef {
  pick_number: number;
  elapsed_ms: number;
  reserve_used_ms: number;
}

export interface PickSkippedPayload {
  skipped_captain_id: number;
  skipped_captain_name: string;
  skipped_captain_avatar_url?: string | null;
  skipped_team_id: number | null;
  skipped_team_name: string | null;
  next_captain_id: number | null;
  next_captain_name: string | null;
  next_captain_avatar_url?: string | null;
  next_team_id: number | null;
  next_team_name: string | null;
  from_pick_number: number;
  to_pick_number: number;
  deferred_to_pick_number: number | null;
  pick_duration_ms: number;
  reserve_used_ms: number;
}

export interface PickSkipUnavailablePayload extends CaptainRef {
  pick_number: number;
}

/**
 * Draft state included in WebSocket messages to avoid additional API calls.
 *
 * The backend sends DraftSerializerSlim (pk-only user references) plus a
 * `_users` dict. The draftWebSocketStore hydrates pk references back to full
 * user objects before storing, so consumers see the same shape as the REST API.
 */
export interface WebSocketDraftState {
  pk: number;
  state: TeamDraftState;
  clock_armed: boolean;
  paused_at: string | null;
  resuming_until: string | null;
  is_manual_pause: boolean;
  draft_options: DraftOptions;
  draft_rounds: Array<{
    pk: number;
    [key: string]: unknown;
  }>;
  users_remaining: Array<{
    pk: number;
    username: string;
    [key: string]: unknown;
  }>;
  latest_round: number | null;
  draft_style: string;
  /** Deduplicated user map from slim serializer (consumed during hydration). */
  _users?: Record<number, Record<string, unknown>>;
  tournament?: {
    pk: number;
    teams: Array<{
      pk: number;
      [key: string]: unknown;
    }>;
  };
}

export interface DraftTickMessage {
  type: "draft_tick";
  draft_state: string;
  server_time: string;
  resuming_until: string | null;
  active_round_pk: number | null;
  active_pick_number: number | null;
  active_captain_id: number | null;
  active_team_id: number | null;
  round_started_at: string | null;
  round_timed_out_at: string | null;
  round_grace_time_ms: number | null;
  teams: Array<{
    team_id: number;
    captain_id: number | null;
    reserve_ms: number | null;
    is_connected: boolean;
    is_ready: boolean;
  }>;
}

export type WebSocketMessage =
  | {
      type: "initial_state";
      draft_state: WebSocketDraftState | null;
      /** Keys are captain pks as strings. */
      captain_fresh?: Record<string, boolean>;
    }
  | { type: "initial_events"; events: DraftEvent[] }
  | { type: "draft_event"; event: DraftEvent; draft_state?: WebSocketDraftState }
  | { type: "captain_heartbeat"; captain_id: number; fresh: boolean }
  | { type: "ping" }
  | DraftTickMessage;
