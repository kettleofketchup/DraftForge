/**
 * Organization API
 *
 * API functions for organization-related operations.
 */

import type { OrganizationType, OrganizationsType } from '~/components/organization/schemas';
import type { UserType } from '~/index';
import type { AddMemberPayload, AddUserResponse } from './types';
import axios from './axios';

interface TransferOwnershipResponse {
  status: string;
  new_owner: UserType;
}

// Discord member type
export interface DiscordMember {
  user: {
    id: string;
    username: string;
    global_name?: string;
    avatar?: string;
  };
  nick?: string;
  joined_at: string;
}

// Organization CRUD
export async function getOrganizations(): Promise<OrganizationsType> {
  const response = await axios.get<OrganizationsType>('/organizations/');
  return response.data;
}

export async function fetchOrganization(pk: number): Promise<OrganizationType> {
  const response = await axios.get<OrganizationType>(`/organizations/${pk}/`);
  return response.data;
}

export async function createOrganization(
  data: Partial<OrganizationType>,
): Promise<OrganizationType> {
  const response = await axios.post<OrganizationType>('/organizations/', data);
  return response.data;
}

export async function updateOrganization(
  pk: number,
  data: Partial<OrganizationType>,
): Promise<OrganizationType> {
  const response = await axios.patch<OrganizationType>(
    `/organizations/${pk}/`,
    data,
  );
  return response.data;
}

export async function deleteOrganization(pk: number): Promise<void> {
  await axios.delete(`/organizations/${pk}/`);
}

// Organization Admin Team
export async function addOrgAdmin(orgId: number, userId: number): Promise<UserType> {
  const response = await axios.post<AddUserResponse>(`/organizations/${orgId}/admins/`, { user_id: userId });
  return response.data.user;
}

export async function removeOrgAdmin(orgId: number, userId: number): Promise<void> {
  await axios.delete(`/organizations/${orgId}/admins/${userId}/`);
}

export async function addOrgStaff(orgId: number, userId: number): Promise<UserType> {
  const response = await axios.post<AddUserResponse>(`/organizations/${orgId}/staff/`, { user_id: userId });
  return response.data.user;
}

export async function removeOrgStaff(orgId: number, userId: number): Promise<void> {
  await axios.delete(`/organizations/${orgId}/staff/${userId}/`);
}

export async function transferOrgOwnership(orgId: number, userId: number): Promise<UserType> {
  const response = await axios.post<TransferOwnershipResponse>(`/organizations/${orgId}/transfer-ownership/`, { user_id: userId });
  return response.data.new_owner;
}

// Organization Users (members via OrgUser)
export async function getOrganizationUsers(orgId: number): Promise<UserType[]> {
  const response = await axios.get<UserType[]>(`/organizations/${orgId}/users/`);
  return response.data;
}

export async function updateOrgUser(
  organizationId: number,
  orgUserId: number,
  data: Partial<UserType>,
): Promise<UserType> {
  const response = await axios.patch<UserType>(
    `/org/${organizationId}/users/${orgUserId}/`,
    data
  );
  return response.data;
}

// Organization Discord Members
export async function getOrganizationDiscordMembers(orgId: number): Promise<DiscordMember[]> {
  const response = await axios.get<{ members: DiscordMember[] }>(`/discord/organizations/${orgId}/discord-members/`);
  return response.data.members;
}

// Profile Claim Request types
export interface ProfileClaimRequest {
  id: number;
  claimer: number;
  claimer_username: string;
  claimer_discord_id: string | null;
  claimer_avatar: string | null;
  target_user: number;
  target_nickname: string | null;
  target_steamid: number | null;
  target_mmr: number | null;
  organization: number;
  organization_name: string;
  status: 'pending' | 'approved' | 'rejected';
  reviewed_by: number | null;
  reviewed_by_username: string | null;
  rejection_reason: string;
  created_at: string;
  reviewed_at: string | null;
}

// Profile Claim Request API
export async function getClaimRequests(options?: {
  status?: 'pending' | 'approved' | 'rejected';
  organizationId?: number;
}): Promise<ProfileClaimRequest[]> {
  const params = new URLSearchParams();
  if (options?.status) {
    params.append('status', options.status);
  }
  if (options?.organizationId) {
    params.append('organization', options.organizationId.toString());
  }
  const queryString = params.toString() ? `?${params.toString()}` : '';
  const response = await axios.get<ProfileClaimRequest[]>(`/claim-requests/${queryString}`);
  return response.data;
}

export async function approveClaimRequest(claimId: number): Promise<{ message: string }> {
  const response = await axios.post<{ message: string }>(`/claim-requests/${claimId}/approve/`);
  return response.data;
}

export async function rejectClaimRequest(claimId: number, reason?: string): Promise<{ message: string }> {
  const response = await axios.post<{ message: string }>(`/claim-requests/${claimId}/reject/`, { reason });
  return response.data;
}

// Organization Members
export async function addOrgMember(
  orgId: number,
  payload: AddMemberPayload,
): Promise<UserType> {
  const response = await axios.post<AddUserResponse>(
    `/organizations/${orgId}/members/`,
    payload,
  );
  return response.data.user;
}

// Discord member search
export interface DiscordSearchResult {
  user: {
    id: string;
    username: string;
    global_name?: string;
    avatar?: string;
  };
  nick?: string;
  has_site_account: boolean;
  site_user_pk: number | null;
}

export async function searchDiscordMembers(
  orgId: number,
  query: string,
): Promise<DiscordSearchResult[]> {
  const response = await axios.get<{ results: DiscordSearchResult[] }>(
    `/discord/search-discord-members/`,
    { params: { q: query, org_id: orgId } },
  );
  return response.data.results;
}

export async function refreshDiscordMembers(
  orgId: number,
): Promise<{ refreshed: boolean; count: number }> {
  const response = await axios.post<{ refreshed: boolean; count: number }>(
    `/discord/refresh-discord-members/`,
    { org_id: orgId },
  );
  return response.data;
}
