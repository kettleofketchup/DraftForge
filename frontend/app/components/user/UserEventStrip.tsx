import { memo, useMemo } from 'react';
import { PlayerPopover } from '~/components/player';
import { Badge } from '~/components/ui/badge';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '~/components/ui/tooltip';
import { DisplayName } from '~/components/user/avatar';
import { RolePositions } from '~/components/user/positions';
import { UserAvatar } from '~/components/user/UserAvatar';
import { cn } from '~/lib/utils';
import type { UserType } from './types';

/** Dota profile data from EventSignupSerializer.dota_profile */
export interface DotaProfileData {
  unverified_friend_id: string | null;
  positions: {
    pos_1: boolean;
    pos_2: boolean;
    pos_3: boolean;
    pos_4: boolean;
    pos_5: boolean;
  };
  rank_status: string;
  rank_medal: string | null;
  mmr: number | null;
  rank_screenshot: string | null;
  battlecup_screenshot: string | null;
  battle_cup_tier: number | null;
}

interface UserEventStripProps {
  user: UserType;
  dotaProfile?: DotaProfileData | null;

  /** Slot for status badge (signup status, position number) */
  contextSlot?: React.ReactNode;

  /** Slot for admin action buttons */
  actionSlot?: React.ReactNode;

  className?: string;
  'data-testid'?: string;
}

/**
 * Convert DotaProfile boolean positions to the UserType.positions format
 * that RolePositions expects (number = preference rank, 0 = not selected).
 */
export function dotaProfileToPositions(
  positions: DotaProfileData['positions'] | undefined,
): UserType['positions'] | null {
  if (!positions) return null;
  // Assign rank 1 to all selected positions (DotaProfile doesn't track preference order)
  return {
    carry: positions.pos_1 ? 1 : 0,
    mid: positions.pos_2 ? 1 : 0,
    offlane: positions.pos_3 ? 1 : 0,
    soft_support: positions.pos_4 ? 1 : 0,
    hard_support: positions.pos_5 ? 1 : 0,
  };
}

/**
 * Event signup strip showing user info + Dota 2 profile data.
 * Used on the event page signups/waitlist tabs.
 *
 * Layout: [Avatar] [Name + Positions] [Medal/MMR] [Context] [Actions]
 */
export const UserEventStrip = memo(
  ({
    user,
    dotaProfile,
    contextSlot,
    actionSlot,
    className,
    'data-testid': testId,
  }: UserEventStripProps) => {
    const { fullName, displayedName } = useMemo(
      () => ({
        fullName: DisplayName(user),
        displayedName: DisplayName(user, 20),
      }),
      [user?.username, user?.nickname],
    );

    // Build a fake user object with positions for RolePositions component
    const userWithPositions = useMemo(() => {
      const positions = dotaProfileToPositions(dotaProfile?.positions);
      if (!positions) return null;
      return { ...user, positions } as UserType;
    }, [user, dotaProfile?.positions]);

    // Medal + MMR display
    const rankDisplay = useMemo(() => {
      if (!dotaProfile) return null;
      const parts: React.ReactNode[] = [];

      if (dotaProfile.rank_medal) {
        parts.push(
          <Badge
            key="medal"
            variant="outline"
            className="px-1.5 py-0 text-xs font-medium text-amber-300 border-amber-500/30"
          >
            {dotaProfile.rank_medal}
          </Badge>,
        );
      } else if (dotaProfile.rank_status === 'never' && dotaProfile.battle_cup_tier) {
        parts.push(
          <Badge
            key="tier"
            variant="outline"
            className="px-1.5 py-0 text-xs font-medium text-blue-300 border-blue-500/30"
          >
            BC T{dotaProfile.battle_cup_tier}
          </Badge>,
        );
      }

      if (dotaProfile.mmr) {
        parts.push(
          <Badge
            key="mmr"
            variant="secondary"
            className="px-1.5 py-0 text-xs font-mono text-white"
          >
            {dotaProfile.mmr.toLocaleString()}
          </Badge>,
        );
      }

      if (dotaProfile.rank_screenshot) {
        parts.push(
          <Tooltip key="ss">
            <TooltipTrigger asChild>
              <Badge
                variant="outline"
                className="px-1 py-0 text-[10px] text-emerald-400 border-emerald-500/30 cursor-help"
              >
                ✓ SS
              </Badge>
            </TooltipTrigger>
            <TooltipContent side="top" className="text-xs">
              Screenshot verified
            </TooltipContent>
          </Tooltip>,
        );
      }

      return parts.length > 0 ? (
        <div className="flex items-center gap-1">{parts}</div>
      ) : null;
    }, [dotaProfile]);

    return (
      <div
        className={cn(
          'flex items-center gap-2 rounded-lg p-1.5 transition-colors',
          'border border-border/50 bg-muted/25 hover:bg-muted/45',
          className,
        )}
        data-testid={testId}
      >
        {/* Avatar */}
        <PlayerPopover player={user}>
          <UserAvatar
            user={user}
            size="md"
            className="cursor-pointer shrink-0"
          />
        </PlayerPopover>

        {/* Name + Positions */}
        <div className="min-w-0 flex flex-col justify-center">
          <PlayerPopover player={user}>
            <span
              className="text-sm font-medium cursor-pointer hover:text-primary transition-colors leading-tight"
              title={fullName.length > 20 ? fullName : undefined}
            >
              {displayedName}
            </span>
          </PlayerPopover>
          {userWithPositions && (
            <div className="mt-0.5">
              <RolePositions user={userWithPositions} compact disableTooltips unranked />
            </div>
          )}
        </div>

        {/* Medal / MMR / Screenshot status */}
        {rankDisplay && (
          <div className="hidden sm:flex items-center gap-1 shrink-0">
            {rankDisplay}
          </div>
        )}

        {/* Context Slot (status badge, position number) */}
        {contextSlot && (
          <div className="flex-1 text-right text-xs">{contextSlot}</div>
        )}
        {!contextSlot && <div className="flex-1" />}

        {/* Action Slot (admin buttons) */}
        {actionSlot && <div className="shrink-0">{actionSlot}</div>}
      </div>
    );
  },
);

UserEventStrip.displayName = 'UserEventStrip';
