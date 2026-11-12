import type React from 'react';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '~/components/ui/tooltip';
import type { LeagueDistribution } from '~/features/league-stats/schemas';
import { cn } from '~/lib/utils';

type Bucket = LeagueDistribution['buckets'][number];

const bucketRange = (b: Bucket): string => `${b.min}–${b.max}%`;
const bucketLabel = (b: Bucket): string =>
  `${bucketRange(b)}: ${b.count} ${b.count === 1 ? 'player' : 'players'}`;

const COL_START = [
  'col-start-1',
  'col-start-2',
  'col-start-3',
  'col-start-4',
  'col-start-5',
  'col-start-6',
  'col-start-7',
  'col-start-8',
  'col-start-9',
  'col-start-10',
] as const;

function labelPosition(index: number, total: number): string {
  const align =
    index === 0
      ? 'justify-self-start'
      : index === total - 1
        ? 'justify-self-end'
        : 'justify-self-center';
  return cn(COL_START[index], align);
}

export const WinRateHistogram: React.FC<{
  distribution: LeagueDistribution;
  population: number;
  minGames: number;
  highlightBucket: number | null;
}> = ({ distribution, population, minGames, highlightBucket }) => {
  const { buckets } = distribution;
  const maxCount = Math.max(1, ...buckets.map((b) => b.count));
  const highlighted =
    highlightBucket !== null ? buckets[highlightBucket] : undefined;
  const label =
    highlightBucket !== null
      ? labelPosition(highlightBucket, buckets.length)
      : null;

  return (
    <div data-testid="win-rate-histogram" className="flex flex-col gap-1">
      <p className="text-xs text-muted-foreground">
        Win-rate distribution · {population} ranked players (≥{minGames} games)
      </p>
      {population === 0 ? (
        <p className="text-sm text-muted-foreground">No ranked players yet</p>
      ) : (
        <>
          <div className="relative h-[90px] pt-[14px]">
            {label && (
              <div className="absolute inset-x-0 top-0 grid grid-cols-10 gap-[2px]">
                <span
                  className={cn(
                    'row-start-1 whitespace-nowrap text-[10px] leading-[14px] text-foreground',
                    label,
                  )}
                >
                  this player
                </span>
              </div>
            )}
            <div className="flex h-full items-end gap-[2px]">
              {buckets.map((b, i) => {
                const isHighlighted = i === highlightBucket;
                return (
                  <Tooltip key={b.min}>
                    <TooltipTrigger asChild>
                      <div
                        data-testid="histogram-bar"
                        role="img"
                        aria-label={bucketLabel(b)}
                        tabIndex={0}
                        className="flex h-full flex-1 items-end rounded-[2px] outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      >
                        {b.count === 0 ? (
                          <div data-empty="true" className="h-px w-full bg-border" />
                        ) : (
                          <svg
                            data-fill
                            aria-hidden="true"
                            width="100%"
                            height={`${(b.count / maxCount) * 100}%`}
                            data-highlighted={isHighlighted ? 'true' : undefined}
                            className={cn(
                              'block min-h-[4px] rounded-t-[4px]',
                              isHighlighted
                                ? 'bg-foreground ring-1 ring-primary'
                                : 'bg-muted-foreground/70',
                            )}
                          />
                        )}
                      </div>
                    </TooltipTrigger>
                    <TooltipContent>{bucketLabel(b)}</TooltipContent>
                  </Tooltip>
                );
              })}
            </div>
          </div>
          <div className="flex justify-between text-[10px] text-muted-foreground">
            <span>0%</span>
            <span>50%</span>
            <span>100%</span>
          </div>
          <p className="text-xs text-muted-foreground">
            {highlighted ? `bucket ${bucketRange(highlighted)}` : 'not ranked yet'}
          </p>
          <table className="sr-only">
            <caption>Players per win-rate bucket</caption>
            <thead>
              <tr>
                <th scope="col">Bucket</th>
                <th scope="col">Players</th>
              </tr>
            </thead>
            <tbody>
              {buckets.map((b, i) => (
                <tr key={b.min}>
                  <td>
                    {bucketRange(b)}
                    {i === highlightBucket ? ' (this player)' : ''}
                  </td>
                  <td>{b.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
};
