/**
 * Team API
 *
 * API functions for team-related operations.
 */

import { z } from 'zod';
import type { TeamsType, TeamType } from '~/index';
import axios from './axios';

// TeamUsage in backend/app/services/team_references.py
export const TeamUsageSchema = z.object({
  model: z.string(),
  label: z.string(),
  label_plural: z.string(),
  count: z.number(),
  teams: z.array(z.object({ pk: z.number(), name: z.string() })),
});
export type TeamUsage = z.infer<typeof TeamUsageSchema>;

export const TeamUsageCheckSchema = z.object({
  in_use: z.boolean(),
  detail: z.string().nullable(),
  usage: z.array(TeamUsageSchema),
});
export type TeamUsageCheck = z.infer<typeof TeamUsageCheckSchema>;

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

/** Resolves to undefined when the PATCH emptied the team and it was deleted (204). */
export async function updateTeam(
  pk: number,
  data: Partial<TeamType>,
): Promise<TeamType | undefined> {
  const response = await axios.patch<TeamType>(`/teams/${pk}/`, data);
  return response.status === 204 ? undefined : response.data;
}

export async function deleteTeam(pk: number): Promise<void> {
  await axios.delete(`/teams/${pk}/`);
}

/** What would stop DELETE /teams/{pk}/, without deleting. */
export async function fetchTeamUsage(pk: number): Promise<TeamUsageCheck> {
  const response = await axios.get(`/teams/${pk}/usage/`);
  return TeamUsageCheckSchema.parse(response.data);
}
