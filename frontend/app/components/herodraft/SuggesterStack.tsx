import { memo } from 'react';
import { UserAvatar } from '~/components/user/UserAvatar';
import { cn } from '~/lib/utils';
import type { Suggester } from './chat/suggestions';

export const MAX_SUGGESTER_AVATARS = 3;

const AVATAR_SIZE = 'h-3 w-3 md:h-3.5 md:w-3.5 lg:h-4 lg:w-4 2xl:h-5 2xl:w-5';

export interface SuggesterStackProps {
  users: readonly Suggester[];
  kind: 'pick' | 'ban';
  heroId: number;
}

/** Overlapping suggester avatars: picks top-left in green, bans bottom-right in red. */
export const SuggesterStack = memo(function SuggesterStack({
  users,
  kind,
  heroId,
}: SuggesterStackProps) {
  if (users.length === 0) return null;
  const shown = users.slice(-MAX_SUGGESTER_AVATARS);
  const extra = users.length - shown.length;
  const ring = kind === 'pick' ? 'ring-pick' : 'ring-ban';
  return (
    <span
      className={cn(
        'pointer-events-none absolute z-10 flex -space-x-1',
        kind === 'pick'
          ? '-top-1 -left-1'
          : '-bottom-1 -right-1 flex-row-reverse space-x-reverse',
      )}
      data-testid={`herodraft-hero-${heroId}-${kind}-suggesters`}
      data-count={users.length}
    >
      {shown.map((user) => (
        <UserAvatar
          key={user.pk}
          user={user}
          size="tiny"
          className={cn(AVATAR_SIZE, 'ring-1', ring)}
        />
      ))}
      {extra > 0 && (
        <span
          className={cn(
            AVATAR_SIZE,
            'flex items-center justify-center rounded-full bg-card text-[6px] font-semibold leading-none text-foreground ring-1 lg:text-[7px]',
            ring,
          )}
          data-testid={`herodraft-hero-${heroId}-${kind}-suggesters-more`}
        >
          +{extra}
        </span>
      )}
    </span>
  );
});
