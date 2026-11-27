import { useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { toast } from 'sonner';
import { organizationQueryKey } from '~/components/organization/hooks/useOrganization';
import { invalidatePermissionChecks } from '~/features/discord-permissions/lifecycle';
import { useLatestSearchParams } from '~/hooks/useLatestSearchParams';
import { discordConnectKeys } from './queries';
import { DiscordConnectErrorSchema, type DiscordConnectError } from './schemas';

const ERROR_MESSAGES: Record<DiscordConnectError, string> = {
  cancelled: 'Discord connection was cancelled.',
  expired: 'That Discord link expired. Start the connection again.',
  forbidden: 'Only organization admins can connect Discord.',
  invalid_server: 'Discord did not return a server. Try again.',
  bot_missing:
    "The DraftForge bot couldn't see that server. Add the bot and try again.",
};

/**
 * Toast the `?discord=connected|error&reason=` result the install callback appends.
 * The callback is a full page load, so the toast waits a task for the Toaster to subscribe.
 */
export function useDiscordConnectResult(orgId?: number): void {
  const [searchParams, setSearchParams] = useLatestSearchParams();
  const queryClient = useQueryClient();
  const result = searchParams.get('discord');
  const reason = searchParams.get('reason');

  useEffect(() => {
    if (!result) return;
    if (result === 'connected') {
      setTimeout(() => toast.success('Discord server connected'), 0);
      void invalidatePermissionChecks(queryClient, {}, 'remove').then(() => {
        if (orgId != null) {
          void queryClient.invalidateQueries({
            queryKey: organizationQueryKey(orgId),
          });
          void queryClient.invalidateQueries({
            queryKey: discordConnectKeys.botStatus(orgId),
          });
        }
      });
    } else {
      const parsed = DiscordConnectErrorSchema.safeParse(reason);
      const message = parsed.success
        ? ERROR_MESSAGES[parsed.data]
        : 'Could not connect Discord.';
      setTimeout(() => toast.error(message), 0);
    }
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.delete('discord');
        next.delete('reason');
        return next;
      },
      { replace: true, preventScrollReset: true },
    );
  }, [result, reason, orgId, queryClient, setSearchParams]);
}
