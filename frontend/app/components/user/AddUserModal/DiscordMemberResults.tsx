import React, { useCallback, useState } from 'react';
import { Button } from '~/components/ui/button';
import { RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { DiscordMemberStrip } from '~/components/user/DiscordMemberStrip';
import type { DiscordMemberResultsProps } from './types';
import type { AddMemberPayload, DiscordSearchResult } from '~/components/api/api';

export const DiscordMemberResults: React.FC<DiscordMemberResultsProps> = ({
  results,
  loading,
  onAdd,
  isAdded,
  isDiscordUserAdded,
  entityLabel,
  onRefresh,
  refreshing,
  hasDiscordServer,
}) => {
  const [addingId, setAddingId] = useState<string | null>(null);

  const handleAdd = useCallback(
    async (member: DiscordSearchResult) => {
      const discordId = member.user.id;
      setAddingId(discordId);
      try {
        // Backend resolves Discord data from its own cache -- just send the ID
        const payload: AddMemberPayload = member.has_site_account
          ? { user_id: member.site_user_pk! }
          : { discord_id: member.user.id };
        await onAdd(payload);
        toast.success(
          `Added ${member.nick || member.user.global_name || member.user.username}`
        );
      } catch (err) {
        toast.error(
          err instanceof Error ? err.message : 'Failed to add user'
        );
      } finally {
        setAddingId(null);
      }
    },
    [onAdd]
  );

  if (!hasDiscordServer) {
    return (
      <div className="py-8 text-center text-sm text-muted-foreground">
        No Discord server configured for this organization
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {/* Refresh button */}
      <Button
        variant="outline"
        className="w-full"
        onClick={onRefresh}
        disabled={refreshing}
      >
        <RefreshCw className={`mr-2 h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
        {refreshing ? 'Refreshing...' : 'Refresh Discord Members'}
      </Button>

      {loading ? (
        <div className="flex items-center justify-center py-8 text-muted-foreground">
          Searching...
        </div>
      ) : results.length === 0 ? (
        <div className="py-8 text-center text-sm text-muted-foreground">
          No Discord members found
        </div>
      ) : (
        <div className="flex flex-col gap-1">
          {results.map((member) => {
            const isDisabled = isDiscordUserAdded(member.user.id);

            return (
              <DiscordMemberStrip
                key={member.user.id}
                member={member}
                onAdd={handleAdd}
                disabled={isDisabled}
                disabledLabel={`Already in ${entityLabel}`}
                adding={addingId === member.user.id}
              />
            );
          })}
        </div>
      )}
    </div>
  );
};
