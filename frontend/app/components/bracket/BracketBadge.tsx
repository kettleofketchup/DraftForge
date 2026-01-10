import { memo } from 'react';
import { cn } from '~/lib/utils';
import { getBadgeColor } from './utils/badgeUtils';

export interface BracketBadgeProps {
  /** The badge letter (A, B, C, etc.) */
  letter: string;
  /** Position relative to the node */
  position: 'right' | 'left';
  /** For losers bracket, which slot this badge is for */
  slot?: 'top' | 'bottom';
  /** Additional CSS classes */
  className?: string;
}

/**
 * Visual badge that links winners bracket games to losers bracket destinations.
 * Displays a colored letter indicating the connection.
 */
export const BracketBadge = memo(function BracketBadge({
  letter,
  position,
  slot,
  className,
}: BracketBadgeProps) {
  const color = getBadgeColor(letter);

  // Position classes based on where badge should appear
  const positionClasses = cn(
    'absolute flex items-center',
    position === 'right' && 'right-0 translate-x-full top-1/2 -translate-y-1/2 pl-1',
    position === 'left' && 'left-0 -translate-x-full pr-1',
    position === 'left' && slot === 'top' && 'top-[25%]',
    position === 'left' && slot === 'bottom' && 'top-[75%]',
    position === 'left' && !slot && 'top-1/2 -translate-y-1/2'
  );

  return (
    <div
      className={cn(positionClasses, className)}
      data-testid={`bracket-badge-${letter}-${position}${slot ? `-${slot}` : ''}`}
    >
      {/* Connecting line */}
      <div
        className={cn(
          'h-px w-3',
          position === 'right' ? 'order-first' : 'order-last'
        )}
        style={{ backgroundColor: color }}
      />
      {/* Badge pill */}
      <div
        className="flex items-center justify-center w-5 h-5 rounded-full text-xs font-bold text-black"
        style={{ backgroundColor: color }}
        data-testid={`bracket-badge-letter-${letter}`}
      >
        {letter}
      </div>
    </div>
  );
});
