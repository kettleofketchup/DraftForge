import { memo } from 'react';
import { TournamentCard } from '~/components/tournament/card/TournamentCard';
import {
  TOURNAMENT_CARD_CELL,
  TOURNAMENT_CARD_SURFACE,
} from '~/components/tournament/card/cardStyles';
import type {
  TournamentBucket,
  TournamentType,
} from '~/components/tournament/types';
import { Skeleton } from '~/components/ui/skeleton';
import { cn } from '~/lib/utils';

// -m-4 cancels the card cell's p-4 so cards line up with the filter row.
const GRID_CLASSES =
  'grid -m-4 self-stretch grid-flow-row-dense content-center justify-center bg-background p-0 grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5';

const GridCell = memo(function GridCell({
  tournament,
  bucket,
  animationIndex,
}: {
  tournament: TournamentType;
  bucket: TournamentBucket;
  animationIndex: number;
}) {
  return (
    <div className="col-span-1 flex h-full content-center gap-4">
      <TournamentCard
        tournament={tournament}
        bucket={bucket}
        animationIndex={animationIndex}
      />
    </div>
  );
});

export function TournamentGrid({
  tournaments,
  bucket,
  testId,
}: {
  tournaments: TournamentType[];
  bucket: TournamentBucket;
  testId?: string;
}) {
  return (
    <div className={GRID_CLASSES} data-testid={testId}>
      {tournaments.map((t, index) => (
        <GridCell
          key={t.pk ?? `idx-${index}`}
          tournament={t}
          bucket={bucket}
          animationIndex={index}
        />
      ))}
    </div>
  );
}

export function TournamentGridSkeleton({ count = 8 }: { count?: number }) {
  return (
    <div className={GRID_CLASSES} aria-hidden data-testid="tournaments-skeleton">
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className="col-span-1 flex h-full content-center gap-4">
          <div className={TOURNAMENT_CARD_CELL}>
            <div
              data-testid="tournaments-skeleton-card"
              className={cn(TOURNAMENT_CARD_SURFACE, 'pointer-events-none gap-3')}
            >
              <Skeleton className="h-5 w-40" />
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-4 w-1/2" />
              <Skeleton className="h-4 w-2/3" />
              <Skeleton className="mt-auto h-8 w-40" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export function EmptyState({
  testId,
  message,
  showClearHint,
}: {
  testId: string;
  message: string;
  showClearHint: boolean;
}) {
  return (
    <div
      data-testid={testId}
      className="flex flex-col items-center justify-center gap-1 py-16 text-center text-muted-foreground"
    >
      <p className="text-base font-medium">{message}</p>
      {showClearHint && <p className="text-sm">Try clearing filters</p>}
    </div>
  );
}
