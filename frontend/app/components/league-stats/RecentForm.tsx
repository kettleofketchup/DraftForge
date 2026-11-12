import type React from 'react';
import { cn } from '~/lib/utils';

type Result = 'W' | 'L';
type Slot = Result | 'empty';

const SLOT_TITLE: Record<Slot, string> = {
  W: 'Win',
  L: 'Loss',
  empty: 'No game yet',
};

const SLOT_CLASS: Record<Slot, string> = {
  W: 'bg-success',
  L: 'border border-destructive bg-transparent',
  empty: 'flex items-center justify-center',
};

export const RecentForm: React.FC<{
  results: Result[];
  count: number;
  className?: string;
}> = ({ results, count, className }) => {
  const shown = count > 0 ? results.slice(-count) : [];
  const emptyCount = Math.max(0, count - shown.length);
  const slots: Slot[] = [
    ...Array.from({ length: emptyCount }, (): Slot => 'empty'),
    ...shown,
  ];
  const letters = shown.join(' ');
  const label =
    `Last ${count}: ${letters}, oldest to newest` +
    (emptyCount > 0 ? ` (${emptyCount} no game yet)` : '');

  return (
    <div
      data-testid="recent-form"
      role="img"
      aria-label={label}
      className={cn('flex items-center gap-[2px]', className)}
    >
      {slots.map((slot, i) => (
        <span
          key={i}
          data-result={slot}
          title={SLOT_TITLE[slot]}
          className={cn('size-[9px] shrink-0 rounded-[2px]', SLOT_CLASS[slot])}
        >
          {slot === 'empty' && (
            <span className="size-[3px] rounded-full bg-border" />
          )}
        </span>
      ))}
    </div>
  );
};
