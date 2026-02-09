import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Button } from '~/components/ui/button';
import { ScrollArea } from '~/components/ui/scroll-area';
import { RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { DiscordMemberStrip } from '~/components/user/DiscordMemberStrip';
import { cn } from '~/lib/utils';
import type { DiscordMemberResultsProps } from './types';
import type { AddMemberPayload, DiscordSearchResult } from '~/components/api/api';

export const DiscordMemberResults: React.FC<DiscordMemberResultsProps> = ({
  results,
  loading,
  onAdd,
  isDiscordUserAdded,
  onRefresh,
  refreshing,
  hasDiscordServer,
  highlightedIndex,
}) => {
  const [addingId, setAddingId] = useState<string | null>(null);
  const itemRefs = useRef<(HTMLDivElement | null)[]>([]);

  // Scroll highlighted item into view
  useEffect(() => {
    if (highlightedIndex >= 0 && itemRefs.current[highlightedIndex]) {
      itemRefs.current[highlightedIndex]?.scrollIntoView({
        block: 'nearest',
      });
    }
  }, [highlightedIndex]);

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
        <ScrollArea className="h-96">
          <div className="flex flex-col gap-1 p-1 pr-4">
            {results.map((member, index) => {
              const isDisabled = isDiscordUserAdded(member.user.id);
              const highlighted = index === highlightedIndex;

              return (
                <div
                  key={member.user.id}
                  ref={(el) => { itemRefs.current[index] = el; }}
                  className={cn(
                    'rounded-lg',
                    highlighted && 'ring-2 ring-primary ring-offset-1 ring-offset-background',
                  )}
                >
                  <DiscordMemberStrip
                    member={member}
                    onAdd={handleAdd}
                    disabled={isDisabled}
                    disabledLabel="Already added"
                    adding={addingId === member.user.id}
                  />
                </div>
              );
            })}
          </div>
        </ScrollArea>
      )}
    </div>
  );
};
