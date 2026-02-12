/**
 * Game API
 *
 * API functions for game-related operations.
 */

import type { GamesType, GameType } from '~/index';
import axios from './axios';

export async function createGame(data: Partial<GameType>): Promise<GameType> {
  const response = await axios.post(`/game/register`, data);
  return response.data as GameType;
}

export async function getGames(): Promise<GamesType> {
  const response = await axios.get<GamesType>(`/games/`);
  return response.data;
}

export async function fetchGame(pk: number): Promise<GameType> {
  const response = await axios.get<GameType>(`/games/${pk}/`);
  return response.data as GameType;
}

export async function updateGame(
  pk: number,
  data: Partial<GameType>,
): Promise<GameType> {
  const response = await axios.patch<GameType>(`/games/${pk}/`, data);
  return response.data;
}

export async function deleteGame(pk: number): Promise<void> {
  await axios.delete(`/games/${pk}/`);
}
