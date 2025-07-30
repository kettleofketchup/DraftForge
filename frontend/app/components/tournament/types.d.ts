import type { UserType } from '../user/types';
import type { STATE_CHOICES, TOURNAMENT_TYPE } from './constants';

import type { DraftType } from '~/index';

export declare interface TeamType {
  [key: string]: any;
  name?: string;
  date?: string;
  members?: UserType[];
  pk?: number;
  captain?: UserType;
  dropin_members?: UserType[];
  left_members?: UserType[];
  draft?: DraftType;
  tournament?: number;
  current_points?: number;

  // for writing to the database
  members_ids?: number[];
  dropin_member_ids?: number[];
  left_member_ids?: number[];
  captain_id?: number;
}
export declare interface GameType {
  [key: string]: any;

  tournament?: pk;
  round?: number;
  date_played?: string;
  users?: UserType[];
  teams?: Team[];
  pk?: number;
  winning_team?: number;
  state?: STATE_CHOICES;
  tournament_type?: TOURNAMENT_TYPE;
  games?: Game[];
}

export declare interface TournamentType {
  [key: string]: any;

  name?: string;
  date_played?: string;
  users?: UserType[];

  teams?: Team[];

  pk?: number;
  winning_team?: number;
  state?: STATE_CHOICES;
  tournament_type?: TOURNAMENT_TYPE;
  games?: Game[];
  // for writing to the database
  user_ids?: number[];
  team_ids?: number[];
}

export declare interface TournamentClassType extends TournamentType {
  dbFetch: () => Promise<void>;
  dbUpdate: (data: Partial<TournamentType>) => Promise<void>;
  dbCreate: () => Promise<void>;
  dbDelete: () => Promise<void>;
}

export type TournamentsType = TournamentType[];
export type GamesType = GameType[];
export type TeamsType = TeamType[];
