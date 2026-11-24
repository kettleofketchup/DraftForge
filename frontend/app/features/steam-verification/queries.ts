import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';
import { isAxiosError } from 'axios';
import { toast } from 'sonner';
import type { UserType } from '~/components/user/types';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';
import { useUserCacheStore } from '~/store/userCacheStore';
import { useUserStore } from '~/store/userStore';
import { getSteamVerification, setSteamVerification } from './api';
import {
  STEAM_VERIFICATION_DEPENDENT_KEYS,
  steamVerificationKeys,
} from './queryKeys';
import type { SteamVerificationOut } from './schemas';

const log = getLogger('steamVerification');

const MAX_GET_RETRIES = 2;
const ID_CHANGED_MESSAGE =
  'The Friend ID changed; check the new one before verifying.';

function httpStatus(err: unknown): number | undefined {
  return isAxiosError(err) ? err.response?.status : undefined;
}

function isClientError(err: unknown): boolean {
  const status = httpStatus(err);
  return status !== undefined && status >= 400 && status < 500;
}

function apiErrorCode(err: unknown): string | undefined {
  if (!isAxiosError(err)) return undefined;
  const data: unknown = err.response?.data;
  if (!data || typeof data !== 'object') return undefined;
  const { code } = data as { code?: unknown };
  return typeof code === 'string' ? code : undefined;
}

/** Staff-only detail; a 403 means "no access" and callers fall back to the user payload. */
export function useSteamVerification(
  userPk: number,
  opts: { enabled: boolean },
): UseQueryResult<SteamVerificationOut> {
  const viewerPk = useUserStore((s) => s.currentUser?.pk);
  return useQuery({
    queryKey: steamVerificationKeys.detail(userPk, viewerPk),
    queryFn: async () => {
      try {
        return await getSteamVerification(userPk);
      } catch (err) {
        if (httpStatus(err) === 403) {
          log.debug('steam verification not visible', { userPk });
        } else {
          log.warn('steam verification fetch failed', { userPk, err });
        }
        throw err;
      }
    },
    enabled: opts.enabled,
    retry: (failureCount, err) =>
      !isClientError(err) && failureCount < MAX_GET_RETRIES,
  });
}

export interface SetSteamVerificationVars {
  verified: boolean;
  steamAccountId: number;
}

function upsertCachedUser(userPk: number, data: SteamVerificationOut): void {
  const cache = useUserCacheStore.getState();
  const existing = cache.getById(userPk);
  if (!existing) return;
  const patch: UserType = {
    pk: userPk,
    username: existing.username,
    steam_account_id: data.steam_account_id,
    steam_account_verified: data.steam_account_verified,
    steam_account_verified_at: data.steam_account_verified_at,
    steam_account_verified_org_name: data.steam_account_verified_org_name,
    steam_account_exists_checked: data.steam_account_exists_checked,
  };
  cache.upsert(patch);
}

export function useSetSteamVerification(
  userPk: number,
): UseMutationResult<SteamVerificationOut, unknown, SetSteamVerificationVars> {
  const queryClient = useQueryClient();
  const viewerPk = useUserStore((s) => s.currentUser?.pk);
  const detailKey = steamVerificationKeys.detail(userPk, viewerPk);
  return useMutation({
    mutationFn: ({ verified, steamAccountId }: SetSteamVerificationVars) =>
      setSteamVerification(userPk, verified, steamAccountId),
    onSuccess: (data) => {
      queryClient.setQueryData(detailKey, data);
      upsertCachedUser(userPk, data);
      for (const queryKey of STEAM_VERIFICATION_DEPENDENT_KEYS) {
        void queryClient.invalidateQueries({ queryKey });
      }
    },
    onError: (err) => {
      if (httpStatus(err) === 409 && apiErrorCode(err) === 'id_changed') {
        void queryClient.invalidateQueries({ queryKey: detailKey });
        toast.error(ID_CHANGED_MESSAGE);
        return;
      }
      log.error('steam verification update failed', { userPk, err });
      toast.error(extractApiError(err) ?? 'Could not update verification');
    },
  });
}
