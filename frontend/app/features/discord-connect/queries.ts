import {
  useMutation,
  useQuery,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';
import { getDiscordBotStatus, getDiscordInstallLink } from './api';
import type { DiscordBotStatus } from './schemas';

export const discordConnectKeys = {
  botStatus: (orgId: number) => ['discordBotStatus', orgId] as const,
};

export function useDiscordBotStatus(
  orgId: number | undefined,
  enabled: boolean,
): UseQueryResult<DiscordBotStatus> {
  return useQuery({
    queryKey: discordConnectKeys.botStatus(orgId ?? 0),
    queryFn: () => getDiscordBotStatus(orgId!),
    enabled: enabled && orgId != null,
    staleTime: 5 * 60 * 1000,
  });
}

/** Fetch a fresh install link and send the browser to Discord. */
export function useStartDiscordConnect(
  orgId: number,
  navigate: (url: string) => void = (url) => window.location.assign(url),
): UseMutationResult<void, Error, void> {
  return useMutation({
    mutationFn: async () => {
      const { url } = await getDiscordInstallLink(orgId);
      navigate(url);
    },
  });
}
