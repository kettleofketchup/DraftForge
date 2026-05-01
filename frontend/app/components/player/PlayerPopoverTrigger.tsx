import React, { useCallback, useRef } from 'react';
import type { UserType } from '~/components/user/types';
import { useSharedPopover } from '~/components/ui/shared-popover-context';
import { useLeagueStore } from '~/store/leagueStore';
import { useOrgStore } from '~/store/orgStore';

interface PlayerPopoverTriggerProps {
  player: UserType;
  children: React.ReactNode;
}

export const PlayerPopoverTrigger: React.FC<PlayerPopoverTriggerProps> = ({
  player,
  children,
}) => {
  const { showPlayerPopover, hidePopover, openPlayerModal } = useSharedPopover();
  const currentOrg = useOrgStore((s) => s.currentOrg);
  const currentLeague = useLeagueStore((s) => s.currentLeague);
  const triggerRef = useRef<HTMLSpanElement>(null);
  const playerName = player.nickname || player.username || 'Unknown';

  const handleMouseEnter = useCallback(() => {
    if (triggerRef.current) {
      showPlayerPopover(player, triggerRef.current);
    }
  }, [player, showPlayerPopover]);

  const handleMouseLeave = useCallback(() => {
    hidePopover();
  }, [hidePopover]);

  const handleClick = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    openPlayerModal(player, {
      organizationId: currentOrg?.pk,
      leagueId: currentLeague?.pk,
    });
  }, [player, openPlayerModal, currentOrg?.pk, currentLeague?.pk]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      openPlayerModal(player, {
        organizationId: currentOrg?.pk,
        leagueId: currentLeague?.pk,
      });
    } else if (e.key === 'Escape') {
      hidePopover();
    }
  }, [player, openPlayerModal, hidePopover, currentOrg?.pk, currentLeague?.pk]);

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
