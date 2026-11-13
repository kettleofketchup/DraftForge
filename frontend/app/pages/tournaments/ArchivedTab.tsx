import { useEffect, type ReactNode } from 'react';
import type { ArchivedTournamentsResult } from '~/hooks/useTournamentList';
import { SecondaryButton } from '~/components/ui/buttons';
import { getLogger } from '~/lib/logger';
import { ListError } from './ListError';
import { EmptyState, TournamentGrid, TournamentGridSkeleton } from './TournamentGrid';

const log = getLogger('tournaments');

type ArchivedQuery = Pick<
  ArchivedTournamentsResult,
  | 'data'
  | 'tournaments'
  | 'error'
  | 'isError'
  | 'isFetching'
  | 'isPlaceholderData'
  | 'hasNextPage'
  | 'isFetchingNextPage'
  | 'isFetchNextPageError'
  | 'fetchNextPage'
  | 'refetch'
>;

export function ArchivedTab({
  query,
  showClearHint,
}: {
  query: ArchivedQuery;
  showClearHint: boolean;
}) {
  const {
    data,
    tournaments,
    error,
    isError,
    isFetching,
    isPlaceholderData,
    hasNextPage,
    isFetchingNextPage,
    isFetchNextPageError,
    fetchNextPage,
    refetch,
  } = query;
  const failed = isError && !data;

  useEffect(() => {
    if (failed) log.error('Failed to load archived tournaments', error);
  }, [failed, error]);

  useEffect(() => {
    if (isFetchNextPageError) log.error('Failed to load more archived tournaments', error);
  }, [isFetchNextPageError, error]);

  let content: ReactNode;
  if (failed) {
    content = (
      <ListError
        testId="tournaments-error-archived"
        message="Could not load archived tournaments."
        onRetry={() => void refetch()}
      />
    );
  } else if (data === undefined) {
    content = <TournamentGridSkeleton />;
  } else if (tournaments.length === 0) {
    content = (
      <EmptyState
        testId="tournaments-empty-archived"
        message="No archived tournaments"
        showClearHint={showClearHint}
      />
    );
  } else {
    content = (
      <div className="flex flex-col items-center gap-4">
        <TournamentGrid tournaments={tournaments} bucket="archived" />
        {hasNextPage && !isPlaceholderData && (
          <div className="flex flex-wrap items-center justify-center gap-2">
            <SecondaryButton
              data-testid="tournaments-load-more"
              disabled={isFetchingNextPage}
              onClick={() => void fetchNextPage()}
            >
              {isFetchingNextPage ? 'Loading…' : 'Load more'}
            </SecondaryButton>
            {isFetchNextPageError && (
              <>
                <p className="text-sm text-error">Could not load more tournaments.</p>
                <SecondaryButton size="sm" onClick={() => void fetchNextPage()}>
                  Retry
                </SecondaryButton>
              </>
            )}
          </div>
        )}
      </div>
    );
  }

  return (
    <div
      data-testid="tournaments-panel-archived"
      aria-busy={isFetching}
      data-fetching={String(isFetching)}
      className="w-full"
    >
      {content}
    </div>
  );
}
