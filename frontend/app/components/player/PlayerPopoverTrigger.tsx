import React, { useCallback, useRef } from 'react';
import type { GameTypeValue } from '~/components/game/constants';
import { useSharedPopoverActions } from '~/components/ui/shared-popover-context';
import type { UserType } from '~/components/user/types';
import { cn } from '~/lib/utils';
import { useLeagueStore } from '~/store/leagueStore';
import { useOrgStore } from '~/store/orgStore';

interface PlayerPopoverTriggerProps {
  player: UserType;
  children: React.ReactNode;
  statsLeagueId?: number | null;
  /** Context game, forwarded to the hover card and the player modal. */
  gameType?: GameTypeValue;
  /** Accessible name; defaults to "View profile for <name>". */
  label?: string;
  className?: string;
}

export const PlayerPopoverTrigger: React.FC<PlayerPopoverTriggerProps> = ({
  player,
  children,
  statsLeagueId,
  gameType,
  label,
  className,
}) => {
  const {
    showPlayerPopover,
    hidePopover,
    scheduleHidePopover,
    openPlayerModal,
  } = useSharedPopoverActions();
  const currentOrg = useOrgStore((s) => s.currentOrg);
  const currentLeague = useLeagueStore((s) => s.currentLeague);
  const triggerRef = useRef<HTMLSpanElement>(null);
  const playerName = player.nickname || player.username || 'Unknown';
  const game = gameType != null ? { gameType } : {};

  const handleMouseEnter = useCallback(() => {
    if (triggerRef.current) {
      showPlayerPopover(player, triggerRef.current, { statsLeagueId, ...game });
    }
  }, [player, showPlayerPopover, statsLeagueId, gameType]);

  const handleMouseLeave = useCallback(() => {
    scheduleHidePopover();
  }, [scheduleHidePopover]);

  const handleClick = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      openPlayerModal(player, {
        organizationId: currentOrg?.pk,
        leagueId: currentLeague?.pk,
        statsLeagueId,
        ...game,
      });
    },
    [
      player,
      openPlayerModal,
      currentOrg?.pk,
      currentLeague?.pk,
      statsLeagueId,
      gameType,
    ],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        openPlayerModal(player, {
          organizationId: currentOrg?.pk,
          leagueId: currentLeague?.pk,
          statsLeagueId,
          ...game,
        });
      } else if (e.key === 'Escape') {
        hidePopover();
      }
    },
    [
      player,
      openPlayerModal,
      hidePopover,
      currentOrg?.pk,
      currentLeague?.pk,
      statsLeagueId,
      gameType,
    ],
  );

  return (
    <span
      ref={triggerRef}
      className={cn('cursor-pointer', className)}
      role="button"
      tabIndex={0}
      aria-label={label ?? `View profile for ${playerName}`}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
    >
      {children}
    </span>
  );
};
