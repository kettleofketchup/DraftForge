import type { UserType } from '~/index';

export interface AddMemberPayload {
  user_id?: number;
  discord_id?: string;  // Backend looks up Discord data from its own cache
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
}

export interface RebuildDraftRoundsAPI {
  tournament_pk: number;
}

export interface PickPlayerForRoundAPI {
  draft_round_pk: number;
  user_pk: number;
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
