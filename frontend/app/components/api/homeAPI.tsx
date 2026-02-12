/**
 * Home API
 *
 * API functions for home page statistics.
 */

import axios from './axios';

export interface HomeStats {
  tournament_count: number;
  game_count: number;
  organization_count: number;
  league_count: number;
}

export async function getHomeStats(): Promise<HomeStats> {
  const response = await axios.get<HomeStats>('/home-stats/');
  return response.data;
}
