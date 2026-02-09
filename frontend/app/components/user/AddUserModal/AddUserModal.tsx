import React, { useState, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { FormDialog } from '~/components/ui/dialogs/FormDialog';
import { Input } from '~/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import { Search } from 'lucide-react';
import {
  searchUsers,
  searchDiscordMembers,
  refreshDiscordMembers,
} from '~/components/api/api';
import type { AddMemberPayload } from '~/components/api/api';
import { toast } from 'sonner';
import { useDebouncedValue } from '~/hooks/useDebouncedValue';
import { SiteUserResults } from './SiteUserResults';
import { DiscordMemberResults } from './DiscordMemberResults';
import type { AddUserModalProps } from './types';
import type { UserType } from '~/components/user/types';

const DEBOUNCE_MS = 300;
const MIN_QUERY_LENGTH = 3;

export const AddUserModal: React.FC<AddUserModalProps> = ({
  open,
  onOpenChange,
  title,
  entityContext,
  onAdd,
  isAdded,
  hasDiscordServer,
}) => {
  const [query, setQuery] = useState('');
  const debouncedQuery = useDebouncedValue(query, DEBOUNCE_MS);
  const [refreshing, setRefreshing] = useState(false);
  const [addedUsers, setAddedUsers] = useState<Set<number>>(new Set());
  const [addedDiscordIds, setAddedDiscordIds] = useState<Set<string>>(new Set());
  const queryClient = useQueryClient();

  // Site user search via react-query (automatic race condition handling)
  const siteQuery = useQuery({
    queryKey: ['userSearch', debouncedQuery, entityContext.orgId, entityContext.leagueId],
    queryFn: () => searchUsers(debouncedQuery, entityContext.orgId, entityContext.leagueId),
    enabled: open && debouncedQuery.length >= MIN_QUERY_LENGTH,
  });

  // Discord member search via react-query
  const discordQuery = useQuery({
    queryKey: ['discordSearch', debouncedQuery, entityContext.orgId],
    queryFn: () => searchDiscordMembers(entityContext.orgId!, debouncedQuery),
    enabled: open && debouncedQuery.length >= MIN_QUERY_LENGTH && hasDiscordServer && !!entityContext.orgId,
  });

  const siteResults = siteQuery.data ?? [];
  const discordResults = discordQuery.data ?? [];

  // Reset state when modal closes
  const handleOpenChange = useCallback(
    (nextOpen: boolean) => {
      if (!nextOpen) {
        setQuery('');
        setAddedUsers(new Set());
        setAddedDiscordIds(new Set());
      }
      onOpenChange(nextOpen);
    },
    [onOpenChange]
  );

  const handleRefresh = useCallback(async () => {
    if (!entityContext.orgId) return;
    setRefreshing(true);
    try {
      const result = await refreshDiscordMembers(entityContext.orgId);
      toast.success(`Refreshed ${result.count} Discord members`);
      // Invalidate Discord search query to re-fetch
      queryClient.invalidateQueries({ queryKey: ['discordSearch'] });
    } catch {
      toast.error('Failed to refresh Discord members');
    } finally {
      setRefreshing(false);
    }
  }, [entityContext.orgId, queryClient]);

  // Wrap onAdd to track locally added users (optimistic)
  const handleAdd = useCallback(
    async (payload: AddMemberPayload): Promise<void> => {
      const user = await onAdd(payload);
      // Track in local state so isAdded works immediately
      if (user.pk) {
        setAddedUsers((prev) => new Set(prev).add(user.pk!));
      }
      if (payload.discord_id) {
        setAddedDiscordIds((prev) => new Set(prev).add(payload.discord_id!));
        // Invalidate site user search so the new user appears there too
        queryClient.invalidateQueries({ queryKey: ['userSearch'] });
      }
    },
    [onAdd, queryClient]
  );

  const checkIsAdded = useCallback(
    (user: UserType) => {
      if (user.pk && addedUsers.has(user.pk)) return true;
      return isAdded(user);
    },
    [isAdded, addedUsers]
  );

  const checkIsDiscordUserAdded = useCallback(
    (discordId: string) => {
      if (addedDiscordIds.has(discordId)) return true;
      // Check if the Discord user has a linked site account that's already added
      const member = discordResults.find((m) => m.user.id === discordId);
      if (member?.has_site_account && member.site_user_pk) {
        return addedUsers.has(member.site_user_pk) || isAdded({ pk: member.site_user_pk } as UserType);
      }
      return false;
    },
    [addedDiscordIds, addedUsers, discordResults, isAdded]
  );

  return (
    <FormDialog
      open={open}
      onOpenChange={handleOpenChange}
      title={title}
      onSubmit={() => handleOpenChange(false)}
      submitLabel="Done"
      size="full"
      showFooter={false}
      data-testid="add-user-modal"
    >
      {/* Single search bar */}
      <div className="relative mb-4">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Search by username, nickname, or Steam ID..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="pl-9"
          data-testid="add-user-search"
        />
        {/* Loading bar */}
        {siteQuery.isFetching && (
          <div className="absolute bottom-0 left-0 right-0 h-0.5 overflow-hidden rounded-b">
            <div className="h-full w-1/3 bg-primary animate-[loading_1s_ease-in-out_infinite]"
                 style={{ animation: 'loading 1s ease-in-out infinite' }} />
            <style>{`
              @keyframes loading {
                0% { transform: translateX(-100%); }
                100% { transform: translateX(400%); }
              }
            `}</style>
          </div>
        )}
        {query.length > 0 && query.length < MIN_QUERY_LENGTH && (
          <p className="mt-1 text-xs text-muted-foreground">
            Type at least {MIN_QUERY_LENGTH} characters to search
          </p>
        )}
      </div>

      {/* Desktop: two columns */}
      <div className="hidden lg:grid lg:grid-cols-2 lg:gap-4">
        <div>
          <h3 className="mb-2 text-sm font-medium text-foreground">
            Site Users
          </h3>
          <SiteUserResults
            results={siteResults}
            loading={siteQuery.isFetching}
            onAdd={handleAdd}
            isAdded={checkIsAdded}
            queryLength={debouncedQuery.length}
          />
        </div>
        <div>
          <h3 className="mb-2 text-sm font-medium text-foreground">
            Discord Members
          </h3>
          <DiscordMemberResults
            results={discordResults}
            loading={discordQuery.isFetching}
            onAdd={handleAdd}
            isAdded={checkIsAdded}
            isDiscordUserAdded={checkIsDiscordUserAdded}
            orgId={entityContext.orgId}
            onRefresh={handleRefresh}
            refreshing={refreshing}
            hasDiscordServer={hasDiscordServer}
          />
        </div>
      </div>

      {/* Mobile/Tablet: tabs */}
      <div className="lg:hidden">
        <Tabs defaultValue="site">
          <TabsList className="w-full">
            <TabsTrigger value="site" className="flex-1">
              Site Users
            </TabsTrigger>
            <TabsTrigger value="discord" className="flex-1">
              Discord
            </TabsTrigger>
          </TabsList>
          <TabsContent value="site">
            <SiteUserResults
              results={siteResults}
              loading={siteQuery.isFetching}
              onAdd={handleAdd}
              isAdded={checkIsAdded}
              queryLength={debouncedQuery.length}
            />
          </TabsContent>
          <TabsContent value="discord">
            <DiscordMemberResults
              results={discordResults}
              loading={discordQuery.isFetching}
              onAdd={handleAdd}
              isAdded={checkIsAdded}
              isDiscordUserAdded={checkIsDiscordUserAdded}
              orgId={entityContext.orgId}
              onRefresh={handleRefresh}
              refreshing={refreshing}
              hasDiscordServer={hasDiscordServer}
            />
          </TabsContent>
        </Tabs>
      </div>
    </FormDialog>
  );
};
