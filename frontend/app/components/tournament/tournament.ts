import type {
  TeamType,
  GameType,
  TournamentType,
  TournamentClassType,
  STATE_CHOICES,
} from './types';

import type { TOURNAMENT_TYPE } from './constants';
import type { UserType } from '../user/types';

import axios from '~/components/api/axios';
import {
  createTournament,
  createUser,
  deleteTournament,
  deleteUser,
  fetchTournament,
  fetchUser,
  updateTournament,
  updateUser,
} from '~/components/api/api';

export class Tournament implements TournamentClassType {
  name!: string;
  date_played!: string;
  users?: UserType[];
  user_ids?: number[];
  teams?: TeamType[];
  pk?: number;
  winning_team?: number;
  state?: STATE_CHOICES;
  tournament_type?: TOURNAMENT_TYPE;
  games?: GameType[];

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
      console.error('Error fetching user data:', error);
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
      console.error('Error fetching user data:', error);
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
      console.error('Error fetching user data:', error);
      throw error;
    }
  }
  async dbCreate(): Promise<void> {
    try {
      await createTournament(this as TournamentType);
    } catch (error) {
      console.error('Error creating user data:', error);
      throw error;
    }
  }
  // Mutates the current instance with values from a GuildMember
}
