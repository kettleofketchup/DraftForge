import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo } from 'react';
import { getDiscordChannels, getDiscordRoles } from '~/components/api/api';
import { getLogger } from '~/lib/logger';
import { discordKeys } from './queryKeys';
import type { DiscordResolver } from './types';

const log = getLogger('discordResolver');
const STALE_MS = 5 * 60_000;

export function useOrgDiscordResolver(
  orgId: number | undefined,
  { enabled }: { enabled: boolean },
): DiscordResolver {
  const active = enabled && !!orgId;
  const roles = useQuery({
    queryKey: discordKeys.roles(orgId ?? 0),
    queryFn: () => getDiscordRoles(orgId as number),
    enabled: active,
    staleTime: STALE_MS,
    retry: false,
  });
  const channels = useQuery({
    queryKey: discordKeys.channels(orgId ?? 0),
    queryFn: () => getDiscordChannels(orgId as number),
    enabled: active,
    staleTime: STALE_MS,
    retry: false,
  });

  useEffect(() => {
    if (roles.error)
      log.warn('discord roles unavailable for preview', roles.error);
  }, [roles.error]);
  useEffect(() => {
    if (channels.error)
      log.warn('discord channels unavailable for preview', channels.error);
  }, [channels.error]);

  return useMemo(() => {
    const resolver: DiscordResolver = {};
    if (active && roles.data)
      resolver.roles = Object.fromEntries(
        roles.data.map((r) => [r.id, { name: r.name, color: r.color }]),
      );
    if (active && channels.data)
      resolver.channels = Object.fromEntries(
        channels.data.map((c) => [c.id, c.name]),
      );
    return resolver;
  }, [active, roles.data, channels.data]);
}
