export type DraftEventType =
  | "draft_started"
  | "draft_completed"
  | "captain_assigned"
  | "player_picked"
  | "tie_roll"
  | "pick_undone";

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
  | PickUndonePayload;

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
  tied_captains: {
    id: number;
    name: string;
    mmr: number;
  }[];
  roll_rounds: {
    captain_id: number;
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

/**
 * Draft state included in WebSocket messages to avoid additional API calls.
 * This matches the DraftSerializerForTournament from the backend.
 */
export interface WebSocketDraftState {
  pk: number;
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
}

export interface WebSocketMessage {
  type: "initial_events" | "draft_event";
  events?: DraftEvent[];
  event?: DraftEvent;
  /** Full draft state included to allow state updates without API calls */
  draft_state?: WebSocketDraftState;
}
