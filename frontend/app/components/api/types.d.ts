import type { UserType } from '~/index';
import type { UserRef } from '~/lib/userDisplayName';

export interface AddMemberPayload {
  user_id?: number;
  discord_id?: string; // Backend looks up Discord data from its own cache
}

export interface AddUserResponse {
  status: string;
  user: UserType;
}

export interface CreateTeamFromCaptainAPI {
  tournament_pk: number;
  user_pk: number;
  draft_order?: number;
}

export interface InitDraftRoundsAPI {
  tournament_pk: number;
  draft_style?: 'snake' | 'normal' | 'shuffle';
  force?: boolean;
}

export interface DraftTeamRef {
  pk: number;
  name: string;
}

/** Distinct records of one kind that use some of the teams. */
export interface DraftTeamUsage {
  /** Model label, e.g. `app.Game` or `app.HeroDraft`. */
  model: string;
  label: string;
  label_plural: string;
  count: number;
  teams: DraftTeamRef[];
}

export type DraftIneligibleReason = 'no_captain' | 'captain_not_in_pool';

export interface DraftResetTeamOutcome {
  pk: number;
  name: string;
  reason: DraftIneligibleReason | (string & {});
  captain?: UserRef | null;
  /** Kept teams only: what uses the team. */
  usage?: DraftTeamUsage[];
}

export interface DraftResetReport {
  reset_teams: number[];
  reset_team_names?: DraftTeamRef[];
  dropped_teams: DraftResetTeamOutcome[];
  kept_teams: DraftResetTeamOutcome[];
  cleared_deputies: { team: number; user: number }[];
}

/** Per-foreign-key counts; a record appears once per column, so never sum them. */
export type DraftReferenceCounts = Record<string, number>;

/** The 409 `draft_reset_has_references` body. */
export interface DraftResetConflict {
  references: DraftReferenceCounts;
  usage: DraftTeamUsage[];
}

export interface RebuildDraftRoundsAPI {
  tournament_pk: number;
}

export interface PickPlayerForRoundAPI {
  draft_round_pk: number;
  user_pk: number;
  client_picked_at?: string;
}

export interface GetDraftStyleMMRsAPI {
  pk: number;
}

export interface DraftStyleMMRsAPIReturn {
  pk: number;
  snake_first_pick_mmr: number;
  snake_last_pick_mmr: number;
  normal_first_pick_mmr: number;
  normal_last_pick_mmr: number;
}

export interface UndoPickAPI {
  draft_pk: number;
}
