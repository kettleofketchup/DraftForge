import type { UserType, UsersType } from '../user/types';
import { STATE_CHOICES } from './tournament';

export enum TOURNAMENT_TYPE {
  single_elimination = 'Single Elimination',
  double_elimination = 'Double Elimination',
  swiss = 'Swiss',
}

export declare interface TeamType {
  name?: string;
  date?: string;
  members?: UserType[];
  pk?: number;
  captain?: UserType;
  dropin_members?: UserType[];
  left_members?: UserType[];

  tournament?: number;
  current_points?: number;
}
export declare interface GameType {
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
  name?: string;
  date_played?: string;
  users?: UserType[];
  teams?: Team[];
  pk?: number;
  winning_team?: number;
  state?: STATE_CHOICES;
  tournament_type?: TOURNAMENT_TYPE;
  games?: Game[];
}

export type TournamentsType = TournamentType[];
export type GamesType = GameType[];
export type TeamsType = TeamType[];
