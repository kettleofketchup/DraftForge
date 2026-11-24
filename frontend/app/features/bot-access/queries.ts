import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';
import { isAxiosError } from 'axios';
import { getBotAccess, httpStatus, refreshBotAccess } from './api';
import type { BotAccessSnapshot } from './schemas';

const MAX_RETRIES = 2;

export const botAccessKeys = {
  league: (leagueId: number) => ['botAccess', leagueId] as const,
};

function shouldRetry(failureCount: number, error: Error): boolean {
  if (!isAxiosError(error)) return false;
  const status = httpStatus(error);
  if (status !== null && status < 500) return false;
  return failureCount < MAX_RETRIES;
}

export function useBotAccess(
  leagueId: number | undefined,
  enabled: boolean,
): UseQueryResult<BotAccessSnapshot> {
  return useQuery({
    queryKey: botAccessKeys.league(leagueId ?? 0),
    queryFn: () => getBotAccess(leagueId!),
    enabled: enabled && leagueId != null,
    staleTime: 30_000,
    retry: shouldRetry,
  });
}

/** Notes from the last refresh live in `mutation.data`; refetches never clear them. */
export function useRefreshBotAccess(
  leagueId: number,
): UseMutationResult<BotAccessSnapshot, unknown, void> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => refreshBotAccess(leagueId),
    onMutate: async () => {
      await queryClient.cancelQueries({
        queryKey: botAccessKeys.league(leagueId),
      });
    },
    onSuccess: (data) => {
      queryClient.setQueryData(botAccessKeys.league(leagueId), data);
    },
  });
}
