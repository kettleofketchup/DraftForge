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

function labelPosition(index: number, total: number): {
  className: string;
  style?: React.CSSProperties;
} {
  if (index === 0) return { className: 'left-0' };
  if (index === total - 1) return { className: 'right-0' };
  return {
    className: '-translate-x-1/2',
    style: { left: `${((index + 0.5) / total) * 100}%` },
  };
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
              <span
                className={cn(
                  'absolute top-0 whitespace-nowrap text-[10px] leading-[14px] text-foreground',
                  label.className,
                )}
                style={label.style}
              >
                this player
              </span>
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
                          <div
                            data-fill
                            data-highlighted={isHighlighted ? 'true' : undefined}
                            className={cn(
                              'w-full min-h-[4px] rounded-t-[4px]',
                              isHighlighted
                                ? 'bg-foreground ring-1 ring-primary'
                                : 'bg-muted-foreground/70',
                            )}
                            style={{ height: `${(b.count / maxCount) * 100}%` }}
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
