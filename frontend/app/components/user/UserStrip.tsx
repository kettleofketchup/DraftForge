import { memo, useMemo } from 'react';
import { PlayerPopover } from '~/components/player';
import { Badge } from '~/components/ui/badge';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '~/components/ui/tooltip';
import { DisplayName } from '~/components/user/avatar';
import { UserAvatar } from '~/components/user/UserAvatar';
import { cn } from '~/lib/utils';
import { RolePositions } from './positions';
import type { UserType } from './types';

interface UserStripProps {
  user: UserType;

  /** Optional slot for contextual data (e.g., projected MMR, pick order) */
  contextSlot?: React.ReactNode;

  /** Optional slot for action button (e.g., Pick, Remove) */
  actionSlot?: React.ReactNode;

  /** Optional league ID for context-specific stats in mini profile */
  leagueId?: number;

  /** Optional organization ID for context-specific stats in mini profile */
  organizationId?: number;

  /** Compact mode - reduced padding, smaller avatar */
  compact?: boolean;

  /** Show border around the strip (default true) */
  showBorder?: boolean;

  /** Additional CSS classes */
  className?: string;

  /** Test ID for the component */
  'data-testid'?: string;
}

const userStripPropsAreEqual = (
  prev: UserStripProps,
  next: UserStripProps,
): boolean => {
  // User identity/display changes
  if (prev.user?.pk !== next.user?.pk) return false;
  if (prev.user?.username !== next.user?.username) return false;
  if (prev.user?.nickname !== next.user?.nickname) return false;
  if (prev.user?.mmr !== next.user?.mmr) return false;
  if ((prev.user as any)?.league_mmr !== (next.user as any)?.league_mmr)
    return false;
  if (prev.user?.avatar !== next.user?.avatar) return false;

  // Positions object - check if both exist or both don't
  const prevHasPos = !!prev.user?.positions;
  const nextHasPos = !!next.user?.positions;
  if (prevHasPos !== nextHasPos) return false;

  // Slots - referential equality (parent should memoize if needed)
  if (prev.contextSlot !== next.contextSlot) return false;
  if (prev.actionSlot !== next.actionSlot) return false;

  // Context IDs
  if (prev.leagueId !== next.leagueId) return false;
  if (prev.organizationId !== next.organizationId) return false;

  // Display options
  if (prev.compact !== next.compact) return false;
  if (prev.showBorder !== next.showBorder) return false;

  // Styling
  if (prev.className !== next.className) return false;

  return true;
};

export const UserStrip = memo(
  ({
    user,
    contextSlot,
    actionSlot,
    leagueId,
    organizationId,
    compact = false,
    showBorder = true,
    className,
    'data-testid': testId,
  }: UserStripProps) => {
    // Type assertion for league_mmr which may not be in base UserType
    const userWithLeague = user as UserType & { league_mmr?: number };

    // Memoize display names to avoid recalculating
    const { fullName, displayedName } = useMemo(
      () => ({
        fullName: DisplayName(user),
        displayedName: DisplayName(user, 20),
      }),
      [user?.username, user?.nickname],
    );

    // Memoize MMR values to prevent badge re-renders
    const baseMmr = useMemo(
      () => (user.mmr ?? 0).toLocaleString().padStart(6, '\u2007'),
      [user.mmr],
    );
    const leagueMmr = useMemo(
      () => (userWithLeague.league_mmr ?? 0).toLocaleString().padStart(6, '\u2007'),
      [userWithLeague.league_mmr],
    );

    // Memoize the entire MMR badge sections to prevent Tooltip/Radix re-renders
    const baseMmrBadge = useMemo(
      () => (
        <Tooltip>
          <TooltipTrigger asChild>
            <Badge
              variant="outline"
              className="px-1.5 py-0 text-xs font-mono cursor-help text-white"
            >
              <span>B:</span>
              <span className="ml-0.5 inline-block min-w-[6ch] text-right">
                {baseMmr}
              </span>
            </Badge>
          </TooltipTrigger>
          <TooltipContent
            side="top"
            className="text-xs bg-popover text-popover-foreground"
          >
            <p className="font-semibold text-foreground">Base MMR</p>
            <p className="text-muted-foreground">Dota 2 ranked MMR</p>
          </TooltipContent>
        </Tooltip>
      ),
      [baseMmr],
    );

    const leagueMmrBadge = useMemo(
      () => (
        <Tooltip>
          <TooltipTrigger asChild>
            <Badge
              variant="secondary"
              className="px-1.5 py-0 text-xs font-mono cursor-help bg-primary/20 text-white"
            >
              <span>L:</span>
              <span className="ml-0.5 inline-block min-w-[6ch] text-right">
                {leagueMmr}
              </span>
            </Badge>
          </TooltipTrigger>
          <TooltipContent
            side="top"
            className="text-xs bg-popover text-popover-foreground"
          >
            <p className="font-semibold text-foreground">League MMR</p>
            <p className="text-muted-foreground">
              Performance-adjusted rating
            </p>
          </TooltipContent>
        </Tooltip>
      ),
      [leagueMmr],
    );

    // Memoize positions to prevent re-renders
    const positions = useMemo(
      () => <RolePositions user={user} compact disableTooltips fillEmpty />,
      [user?.positions],
    );

    return (
      <div
        className={cn(
          'flex items-center gap-2 rounded-lg transition-colors',
          compact ? 'p-1' : 'p-2',
          showBorder && 'border border-border/50',
          'bg-muted/20 hover:bg-muted/40',
          className,
        )}
        data-testid={testId}
      >
        {/* Column 1: Avatar */}
        <PlayerPopover player={user}>
          <UserAvatar
            user={user}
            size={compact ? 'md' : 'lg'}
            className="cursor-pointer shrink-0"
          />
        </PlayerPopover>

        {/* Column 2: Name + Positions (grouped) */}
        <div className="min-w-0 flex flex-col justify-center">
          {/* Row 1: Name */}
          <PlayerPopover player={user}>
            <span
              className="text-sm font-medium cursor-pointer hover:text-primary transition-colors leading-tight"
              title={fullName.length > 12 ? fullName : undefined}
            >
              {displayedName}
            </span>
          </PlayerPopover>
          {/* Row 2: Positions - fillEmpty ensures consistent width */}
          <div className="mt-0.5">{positions}</div>
        </div>

        {/* Column 3: MMR (stacked vertically - Base on top, League below) */}
        <div className="flex flex-col justify-center gap-0.5 shrink-0">
          {baseMmrBadge}
          {leagueMmrBadge}
        </div>

        {/* Column 4: Context Slot (flex-1 to push action to end) */}
        {contextSlot && (
          <div className="flex-1 text-right text-xs">{contextSlot}</div>
        )}

        {/* Spacer when no context slot */}
        {!contextSlot && <div className="flex-1" />}

        {/* Column 5: Action Slot */}
        {actionSlot && <div className="shrink-0">{actionSlot}</div>}
      </div>
    );
  },
  userStripPropsAreEqual,
);

UserStrip.displayName = 'UserStrip';
