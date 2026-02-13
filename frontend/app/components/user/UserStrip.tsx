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
import { isUserEntry, type UserEntry } from '~/store/userCacheTypes';
import { RolePositions } from './positions';
import type { UserType } from './types';

interface UserStripProps {
  user: UserType | UserEntry;

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

  /** Show position badges (default true) */
  showPositions?: boolean;

  /** Additional CSS classes */
  className?: string;

  /** Test ID for the component */
  'data-testid'?: string;
}

const userStripPropsAreEqual = (
  prev: UserStripProps,
  next: UserStripProps,
): boolean => {
  // Entity adapter guarantees new reference = changed data
  if (prev.user !== next.user) return false;

  // Slots - referential equality (parent should memoize if needed)
  if (prev.contextSlot !== next.contextSlot) return false;
  if (prev.actionSlot !== next.actionSlot) return false;

  // Context IDs
  if (prev.leagueId !== next.leagueId) return false;
  if (prev.organizationId !== next.organizationId) return false;

  // Display options
  if (prev.compact !== next.compact) return false;
  if (prev.showBorder !== next.showBorder) return false;
  if (prev.showPositions !== next.showPositions) return false;

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
    showPositions = true,
    className,
    'data-testid': testId,
  }: UserStripProps) => {
    // Memoize display names to avoid recalculating
    const { fullName, displayedName, displayedNameMobile } = useMemo(
      () => ({
        fullName: DisplayName(user),
        displayedName: DisplayName(user, 20),
        displayedNameMobile: DisplayName(user, 15),
      }),
      [user?.username, user?.nickname],
    );

    // Memoize MMR values to prevent badge re-renders
    const orgMmr = isUserEntry(user)
      ? (organizationId ? user.orgData[organizationId]?.mmr : undefined)
      : user.mmr;
    const baseMmr = useMemo(
      () => (orgMmr ?? 0).toLocaleString().padStart(6, '\u2007'),
      [orgMmr],
    );

    const leagueMmrValue = isUserEntry(user)
      ? (leagueId ? user.leagueData[leagueId]?.mmr : undefined)
      : (user as UserType & { league_mmr?: number }).league_mmr;
    const leagueMmr = useMemo(
      () => (leagueMmrValue ?? 0).toLocaleString().padStart(6, '\u2007'),
      [leagueMmrValue],
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
          'bg-muted/25 hover:bg-muted/45',
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
              className="text-sm font-medium cursor-pointer hover:text-primary transition-colors leading-tight inline-block min-w-[15ch] sm:min-w-[20ch]"
              title={fullName.length > 12 ? fullName : undefined}
            >
              <span className="hidden sm:inline">{displayedName}</span>
              <span className="sm:hidden">{displayedNameMobile}</span>
            </span>
          </PlayerPopover>
          {/* Row 2: Positions - fillEmpty ensures consistent width */}
          {showPositions && <div className="mt-0.5">{positions}</div>}
        </div>

        {/* Column 3: MMR (stacked vertically - Base on top, League below) */}
        <div className="flex flex-col justify-center gap-0.5 shrink-0">
          {baseMmrBadge}
          {leagueMmrValue ? leagueMmrBadge : null}
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
