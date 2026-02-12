/**
 * Team API
 *
 * API functions for team-related operations.
 */

import type { TeamsType, TeamType } from '~/index';
import axios from './axios';

export async function createTeam(data: Partial<TeamType>): Promise<TeamType> {
  const response = await axios.post(`/team/register`, data);
  return response.data as TeamType;
}

export async function getTeams(): Promise<TeamsType> {
  const response = await axios.get<TeamsType>(`/teams/`);
  return response.data as TeamsType;
}

export async function fetchTeam(pk: number): Promise<TeamType> {
  const response = await axios.get<TeamType>(`/teams/${pk}/`);
  return response.data as TeamType;
}

export async function updateTeam(
  pk: number,
  data: Partial<TeamType>,
): Promise<TeamType> {
  const response = await axios.patch<TeamType>(`/teams/${pk}/`, data);
  return response.data;
}

export async function deleteTeam(pk: number): Promise<void> {
  await axios.delete(`/teams/${pk}/`);
}
