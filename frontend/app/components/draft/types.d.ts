import type { TournamentType, UserType } from '~/index';

export interface DraftType {
  [key: string]: any;
  tournament?: TournamentType;
  users_remaining?: UserType[];
  draft_rounds?: DraftRoundType[];
}

export interface DraftRoundType {
  [key: string]: any;
  draft?: DraftType;
  captain?: UserType;
  pick_number?: number;
  pick_phase?: number;
  choice?: UserType;
}
