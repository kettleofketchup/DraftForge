import type { TeamType, TournamentType, UserType } from '~/index';

export interface DraftType {
  [key: string]: any;
  pk?: number;
  tournament?: TournamentType;
  users_remaining?: UserType[];
  draft_rounds?: DraftRoundType[];
  latest_round?: number;
}

export interface DraftRoundType {
  [key: string]: any;
  pk?: number;
  draft?: DraftType;
  captain?: UserType;
  pick_number?: number;
  pick_phase?: number;
  choice?: UserType;
  team?: TeamType;
}
