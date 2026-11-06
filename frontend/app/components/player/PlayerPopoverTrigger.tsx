import React, { useCallback, useRef } from 'react';
import type { UserType } from '~/components/user/types';
import { useSharedPopoverActions } from '~/components/ui/shared-popover-context';
import { useLeagueStore } from '~/store/leagueStore';
import { useOrgStore } from '~/store/orgStore';

interface PlayerPopoverTriggerProps {
  player: UserType;
  children: React.ReactNode;
  statsLeagueId?: number | null;
}

export const PlayerPopoverTrigger: React.FC<PlayerPopoverTriggerProps> = ({
  player,
  children,
  statsLeagueId,
}) => {
  const { showPlayerPopover, hidePopover, openPlayerModal } = useSharedPopoverActions();
  const currentOrg = useOrgStore((s) => s.currentOrg);
  const currentLeague = useLeagueStore((s) => s.currentLeague);
  const triggerRef = useRef<HTMLSpanElement>(null);
  const playerName = player.nickname || player.username || 'Unknown';

  const handleMouseEnter = useCallback(() => {
    if (triggerRef.current) {
      showPlayerPopover(player, triggerRef.current, { statsLeagueId });
    }
  }, [player, showPlayerPopover, statsLeagueId]);

  const handleMouseLeave = useCallback(() => {
    hidePopover();
  }, [hidePopover]);

  const handleClick = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    openPlayerModal(player, {
      organizationId: currentOrg?.pk,
      leagueId: currentLeague?.pk,
      statsLeagueId,
    });
  }, [player, openPlayerModal, currentOrg?.pk, currentLeague?.pk, statsLeagueId]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      openPlayerModal(player, {
        organizationId: currentOrg?.pk,
        leagueId: currentLeague?.pk,
        statsLeagueId,
      });
    } else if (e.key === 'Escape') {
      hidePopover();
    }
  }, [player, openPlayerModal, hidePopover, currentOrg?.pk, currentLeague?.pk, statsLeagueId]);

  return (
    <span
      ref={triggerRef}
      className="cursor-pointer"
      role="button"
      tabIndex={0}
      aria-label={`View profile for ${playerName}`}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
    >
      {children}
    </span>
  );
};
