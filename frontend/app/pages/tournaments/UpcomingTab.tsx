import type { UseQueryResult } from '@tanstack/react-query';
import { useEffect, useId, type ReactNode } from 'react';
import type { TournamentsType, TournamentType } from '~/components/tournament/types';
import { SecondaryButton } from '~/components/ui/buttons';
import { getLogger } from '~/lib/logger';
import { showsSignupsOpenBadge } from '~/components/tournament/orgScope';
import {
  BrowseAllButton,
  EmptyState,
  TournamentGrid,
  TournamentGridSkeleton,
} from './TournamentGrid';
import type { Membership } from './useMembership';
import { resolveUpcomingView } from './upcomingView';
import { ListError } from './ListError';

const log = getLogger('tournaments');

const TIER_HEADING =
  'text-sm font-semibold uppercase tracking-wide text-muted-foreground';

function Tier({
  tier,
  title,
  tournaments,
  children,
}: {
  tier: 'yours' | 'others';
  title: string;
  tournaments: TournamentType[];
  children?: ReactNode;
}) {
  const headingId = useId();
  return (
    <section data-tier={tier} aria-labelledby={headingId} className="flex flex-col gap-3">
      <h2 id={headingId} data-testid={`tournaments-tier-${tier}`} className={TIER_HEADING}>
        {title} <span>({tournaments.length})</span>
      </h2>
      {children}
      {tournaments.length > 0 && (
        <TournamentGrid tournaments={tournaments} bucket="upcoming" />
      )}
    </section>
  );
}

export function UpcomingTab({
  query,
  membership,
  orgOrLeagueFilter,
  mine,
  showClearHint,
  onViewArchived,
  onBrowseAll,
}: {
  query: Pick<UseQueryResult<TournamentsType>, 'data' | 'isError' | 'isFetching' | 'refetch' | 'error'>;
  membership: Membership;
  orgOrLeagueFilter: boolean;
  mine: boolean;
  showClearHint: boolean;
  onViewArchived: () => void;
  onBrowseAll: () => void;
}) {
  const { data, isError, isFetching, refetch, error } = query;
  const failed = isError && !data;

  useEffect(() => {
    if (failed) log.error('Failed to load upcoming tournaments', error);
  }, [failed, error]);

  const view = resolveUpcomingView({
    data,
    membershipPending: membership.membershipPending,
    isLoggedIn: membership.isLoggedIn,
    memberOrgIds: membership.memberOrgIds,
    orgOrLeagueFilter,
  });

  let content: ReactNode;
  if (failed) {
    content = (
      <ListError
        testId="tournaments-error-upcoming"
        message="Could not load upcoming tournaments."
        onRetry={() => void refetch()}
      />
    );
  } else if (view.kind === 'skeleton') {
    content = <TournamentGridSkeleton />;
  } else if (view.kind === 'empty') {
    content = (
      <EmptyState
        testId="tournaments-empty-upcoming"
        message={
          mine
            ? 'No upcoming tournaments in your organizations or with open signups'
            : 'No upcoming tournaments'
        }
        showClearHint={showClearHint}
        action={mine ? <BrowseAllButton onClick={onBrowseAll} /> : undefined}
      />
    );
  } else if (view.kind === 'flat') {
    const memberOrgIds = membership.memberOrgIds;
    content = (
      <TournamentGrid
        tournaments={view.items}
        bucket="upcoming"
        showSignupsOpen={
          mine ? (t) => showsSignupsOpenBadge(t, memberOrgIds) : undefined
        }
      />
    );
  } else {
    content = (
      <div className="flex flex-col gap-8">
        <Tier tier="yours" title="Your organizations" tournaments={view.yours}>
          {view.yours.length === 0 && (
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-sm text-muted-foreground">
                No upcoming tournaments in your organizations.
              </p>
              <SecondaryButton
                size="sm"
                data-testid="tournaments-empty-yours-archived-link"
                onClick={onViewArchived}
              >
                View archived
              </SecondaryButton>
            </div>
          )}
        </Tier>
        {view.others.length > 0 && (
          <Tier tier="others" title="Other organizations" tournaments={view.others} />
        )}
      </div>
    );
  }

  return (
    <div
      data-testid="tournaments-panel-upcoming"
      aria-busy={isFetching}
      data-fetching={String(isFetching)}
      className="w-full"
    >
      {content}
    </div>
  );
}
