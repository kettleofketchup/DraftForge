/**
 * User Profile API
 *
 * Layered profile GET and base PATCH. gameUser and orgProfiles are
 * present in the response; orgProfiles is still empty.
 */

import type {
  DeadlockUserProfile,
  DotaUserProfile,
  PositionsValue,
  UserProfileEntry,
} from '~/store/userProfileTypes';

import axios from './axios';

export interface BasePatchPayload {
  nickname?: string | null;
  avatar?: string | null;
}

export interface BasePatchResponse {
  nickname?: string | null;
  avatar?: string | null;
}

/**
 * Fetch the current user's layered profile.
 *
 * `orgProfiles` is present but empty. The `_userPk` argument is unused (the
 * endpoint is `/me/`-only) and is kept for when the endpoint accepts a pk.
 */
export async function getUserProfile(
  _userPk: number,
): Promise<UserProfileEntry> {
  const response = await axios.get('/users/me/profile/');
  return {
    ...response.data,
    _fetchedAt: Date.now(),
  };
}

/**
 * PATCH /api/users/me/profile/base/ — partial update of BaseUserProfile
 * fields (nickname, avatar). Returns the updated base layer.
 */
export async function patchBaseProfile(
  patch: BasePatchPayload,
): Promise<BasePatchResponse> {
  const response = await axios.patch<BasePatchResponse>(
    '/users/me/profile/base/',
    patch,
  );
  return response.data;
}

export type DotaPatchPayload = {
  positions?: PositionsValue | null;
  has_active_dota_mmr?: boolean;
};
export type DeadlockPatchPayload = {
  rank?: string | null;
  rank_date?: string | null;
};

// OVERLOADS — without them the union return makes `updated.positions` a TS2339
// in DotaTab.onSuccess (DeadlockUserProfile has no `positions`). The overloads
// narrow the return per game so each tab's onSuccess is typed.
export async function patchGameProfile(
  game: 'dota',
  patch: DotaPatchPayload,
): Promise<DotaUserProfile>;
export async function patchGameProfile(
  game: 'deadlock',
  patch: DeadlockPatchPayload,
): Promise<DeadlockUserProfile>;
export async function patchGameProfile(
  game: 'dota' | 'deadlock',
  patch: DotaPatchPayload | DeadlockPatchPayload,
): Promise<DotaUserProfile | DeadlockUserProfile> {
  const response = await axios.patch<DotaUserProfile | DeadlockUserProfile>(
    `/users/me/profile/game/${game}/`,
    patch,
  );
  return response.data;
}
