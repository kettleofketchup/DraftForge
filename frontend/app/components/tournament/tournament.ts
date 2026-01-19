import type {
  GameType,
  TeamType,
  TournamentClassType,
  TournamentType,
} from './types';

import type { UserType } from '../user/types.d';
import type { DraftType } from '../draft/types.d';
import type { StateValue, TournamentTypeValue } from './schemas';

import {
  createTournament,
  deleteTournament,
  fetchTournament,
  updateTournament,
} from '~/components/api/api';

import { getLogger } from '~/lib/logger';
const log = getLogger('tournamentClass');
export class Tournament implements TournamentClassType {
  name: string | null = null;
  date_played: string | null = null;
  timezone: string = 'UTC';
  users: UserType[] | null = null;
  user_ids: number[] | null = null;
  teams: TeamType[] | null = null;
  team_ids: number[] | null = null;
  captains: UserType[] | null = null;
  captain_ids: number[] | null = null;
  pk: number | null = null;
  winning_team: number | null = null;
  state: StateValue | null = null;
  tournament_type: TournamentTypeValue | null = null;
  games: GameType[] | null = null;
  draft?: DraftType;
  league?: number | null;
  steam_league_id?: number | null;

  constructor(data: TournamentType) {
    Object.assign(this, data);
  }

  async dbFetch(): Promise<void> {
    if (!this.pk) {
      throw new Error('User primary key (pk) is not set.');
    }
    try {
      const data = await fetchTournament(this.pk);
      Object.assign(this, data);
    } catch (error) {
      log.error('Error fetching user data:', error);
      throw error;
    }
  }

  async dbUpdate(data: Partial<TournamentType>): Promise<void> {
    if (!this.pk) {
      throw new Error('User primary key (pk) is not set.');
    }

    try {
      const updatedData = await updateTournament(this.pk, data);
      Object.assign(this, updatedData);
    } catch (error) {
      log.error('Error fetching user data:', error);
      throw error;
    }
  }

  async dbDelete(): Promise<void> {
    if (!this.pk) {
      throw new Error('User primary key (pk) is not set.');
    }
    try {
      await deleteTournament(this.pk);
      Object.assign({});
    } catch (error) {
      log.error('Error fetching user data:', error);
      throw error;
    }
  }
  async dbCreate(): Promise<void> {
    try {
      await createTournament(this as TournamentType);
    } catch (error) {
      log.error('Error creating user data:', error);
      throw error;
    }
  }
  // Mutates the current instance with values from a GuildMember
}
