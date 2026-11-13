import { useCallback, useRef, useState } from 'react';
import { useSearchParams } from 'react-router';
import { TournamentFilterBar } from '~/components/tournament';
import { TournamentCreateModal } from '~/components/tournament/create/createModal';
import {
  ORG_SCOPE_ALL,
  isDefaultOrgScope,
  isExplicitOrgScope,
  orgScopeRequest,
  parseOrgScope,
} from '~/components/tournament/orgScope';
import {
  filtersActive,
  parseFilterId,
} from '~/components/tournament/tournamentBuckets';
import { PageHeader } from '~/components/ui/page-header';
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  useUrlTabs,
} from '~/components/ui/tabs';
import { useDebouncedValue } from '~/hooks/useDebouncedValue';
import {
  useArchivedTournaments,
  useUpcomingTournaments,
} from '~/hooks/useTournamentList';
import { ArchivedTab } from './ArchivedTab';
import { UpcomingTab } from './UpcomingTab';
import { coerceTab } from './upcomingView';
import { useMembership } from './useMembership';

const SEARCH_DEBOUNCE_MS = 300;

export default function TournamentsPage() {
  const [rawTab, setTab] = useUrlTabs('upcoming');
  const tab = coerceTab(rawTab);
  const [searchParams, setSearchParams] = useSearchParams();
  const membership = useMembership();
  const rawOrganization = searchParams.get('organization');
  const scope = parseOrgScope(rawOrganization, membership.isLoggedIn);
  // Without an explicit scope the default depends on who is logged in.
  const scopeReady = !membership.membershipPending || isExplicitOrgScope(rawOrganization);
  const league = parseFilterId(searchParams.get('league'));
  const [searchInput, setSearchInput] = useState('');
  const search = useDebouncedValue(searchInput, SEARCH_DEBOUNCE_MS);

  const upcoming = useUpcomingTournaments(
    { ...orgScopeRequest(scope, 'upcoming', membership.memberOrgIds), league, search },
    { enabled: scopeReady && tab === 'upcoming' },
  );
  const archived = useArchivedTournaments(
    { ...orgScopeRequest(scope, 'archived', membership.memberOrgIds), league, search },
    { enabled: scopeReady && tab === 'archived' },
  );

  const archivedTriggerRef = useRef<HTMLButtonElement>(null);
  const showArchived = useCallback(() => {
    setTab('archived');
    requestAnimationFrame(() => archivedTriggerRef.current?.focus());
  }, [setTab]);

  const browseAllOrganizations = useCallback(() => {
    const next = new URLSearchParams(searchParams);
    next.set('organization', ORG_SCOPE_ALL);
    next.delete('league');
    setSearchParams(next);
  }, [searchParams, setSearchParams]);

  const showClearHint = filtersActive({
    scopeChanged: !isDefaultOrgScope(scope, membership.isLoggedIn),
    league,
    searchInput,
  });
  const mine = scope.kind === 'mine';
  const orgOrLeagueFilter = scope.kind !== 'all' || league !== undefined;

  return (
    <div className="flex flex-col gap-4 p-4">
      <PageHeader title="Tournaments" actions={<TournamentCreateModal />} />
      <Tabs value={tab} onValueChange={setTab} className="w-full gap-4">
        <TabsList className="self-center">
          <TabsTrigger value="upcoming" data-testid="tournaments-tab-upcoming">
            Upcoming
          </TabsTrigger>
          <TabsTrigger
            ref={archivedTriggerRef}
            value="archived"
            data-testid="tournaments-tab-archived"
          >
            Archived
          </TabsTrigger>
        </TabsList>
        <TournamentFilterBar
          searchInput={searchInput}
          onSearchInputChange={setSearchInput}
          isLoggedIn={membership.isLoggedIn}
          memberOrgIds={membership.memberOrgIds}
          membershipPending={membership.membershipPending}
        />
        <TabsContent value="upcoming">
          <UpcomingTab
            query={upcoming}
            membership={membership}
            orgOrLeagueFilter={orgOrLeagueFilter}
            mine={mine}
            showClearHint={showClearHint}
            onViewArchived={showArchived}
            onBrowseAll={browseAllOrganizations}
          />
        </TabsContent>
        <TabsContent value="archived">
          <ArchivedTab
            query={archived}
            mine={mine}
            showClearHint={showClearHint}
            onBrowseAll={browseAllOrganizations}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}
