/**
 * User API
 *
 * API functions for user, auth, profile, and search operations.
 */

import type {
  GuildMembers,
  UsersType,
  UserType,
} from '~/index';
import { getLogger } from '~/lib/logger';
import axios from './axios';

const log = getLogger('api');

// Auth
export async function fetchCurrentUser(): Promise<UserType> {
  const response = await axios.get<UserType>(`/current_user`);
  return response.data;
}

export async function logout(): Promise<void> {
  await axios.post(`/logout`);
}

// User CRUD
export async function fetchUsers(): Promise<UsersType> {
  await refreshAvatars();
  const response = await axios.get<UsersType>(`/users/`);
  return response.data;
}

export async function fetchUser(pk: number): Promise<UserType> {
  const response = await axios.get<UserType>(`/users/${pk}/`);
  return response.data as UserType;
}

export async function fetchUsersBulk(
  pks: number[],
): Promise<UserType[]> {
  const response = await axios.post<UserType[]>(`/users/bulk/`, {
    pks,
  });
  return response.data;
}

export async function createUser(data: Partial<UserType>): Promise<UserType> {
  const response = await axios.post(`/user/register`, data);
  return response.data as UserType;
}

export async function updateUser(
  userId: number,
  data: Partial<UserType>,
): Promise<UserType> {
  const response = await axios.patch<UserType>(`/users/${userId}/`, data);
  return response.data;
}

export async function deleteUser(userId: number): Promise<void> {
  await axios.delete(`/users/${userId}/`);
}

// Profile
export async function UpdateProfile(
  data: Partial<UserType>,
): Promise<UserType> {
  const response = await axios.post(`/profile_update`, data);
  return response.data as UserType;
}

/**
 * Claim a user profile by merging the target user's data into the current user.
 * This links the current user's Steam account to the target profile.
 * @param targetUserId - The ID of the user profile to claim (must not have Steam ID)
 * @returns The updated current user with merged data
 */
export async function claimUserProfile(targetUserId: number): Promise<UserType> {
  const response = await axios.post<UserType>(`/users/${targetUserId}/claim/`);
  return response.data;
}

// Utility
export async function refreshAvatars(): Promise<void> {
  axios.post(`/avatars/refresh/`);
}

export interface SearchUserResult extends UserType {
  membership?: 'league' | 'org' | 'other_org' | null;
  membership_label?: string | null;
}

export async function searchUsers(
  query: string,
  orgId?: number,
  leagueId?: number,
): Promise<SearchUserResult[]> {
  const params: Record<string, string | number> = { q: query };
  if (orgId) params.org_id = orgId;
  if (leagueId) params.league_id = leagueId;
  const response = await axios.get<SearchUserResult[]>('/users/search/', { params });
  return response.data;
}

export async function get_dtx_members(): Promise<GuildMembers> {
  const response = await axios.get<GuildMembers>(`/discord/dtx_members`);
  if ('members' in response.data) {
    log.debug(response.data.members);
    return response.data.members as GuildMembers;
  } else {
    throw new Error("Key 'members' not found in response data");
  }
}
