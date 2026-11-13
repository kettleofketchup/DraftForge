import { useCallback, useRef, useState } from 'react';
import { useSearchParams } from 'react-router';
import { TournamentFilterBar } from '~/components/tournament';
import { TournamentCreateModal } from '~/components/tournament/create/createModal';
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
  const [searchParams] = useSearchParams();
  const organization = parseFilterId(searchParams.get('organization'));
  const league = parseFilterId(searchParams.get('league'));
  const [searchInput, setSearchInput] = useState('');
  const search = useDebouncedValue(searchInput, SEARCH_DEBOUNCE_MS);
  const params = { organization, league, search };

  const upcoming = useUpcomingTournaments(params, { enabled: tab === 'upcoming' });
  const archived = useArchivedTournaments(params, { enabled: tab === 'archived' });
  const membership = useMembership();

  const archivedTriggerRef = useRef<HTMLButtonElement>(null);
  const showArchived = useCallback(() => {
    setTab('archived');
    requestAnimationFrame(() => archivedTriggerRef.current?.focus());
  }, [setTab]);

  const showClearHint = filtersActive({ organization, league, searchInput });
  const orgOrLeagueFilter = organization !== undefined || league !== undefined;

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
        />
        <TabsContent value="upcoming">
          <UpcomingTab
            query={upcoming}
            membership={membership}
            orgOrLeagueFilter={orgOrLeagueFilter}
            showClearHint={showClearHint}
            onViewArchived={showArchived}
          />
        </TabsContent>
        <TabsContent value="archived">
          <ArchivedTab query={archived} showClearHint={showClearHint} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
