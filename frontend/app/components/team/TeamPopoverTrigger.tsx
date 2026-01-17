import React, { useCallback, useRef } from 'react';
import type { TeamType } from '~/components/tournament/types';
import { useSharedPopover } from '~/components/ui/shared-popover-context';

interface TeamPopoverTriggerProps {
  team: TeamType;
  children: React.ReactNode;
}

export const TeamPopoverTrigger: React.FC<TeamPopoverTriggerProps> = ({
  team,
  children,
}) => {
  const { showTeamPopover, hidePopover, openTeamModal } = useSharedPopover();
  const triggerRef = useRef<HTMLSpanElement>(null);
  const captain = team.captain;
  const teamName = team.name || `${captain?.nickname || captain?.username || 'Unknown'}'s Team`;

  const handleMouseEnter = useCallback(() => {
    if (triggerRef.current) {
      showTeamPopover(team, triggerRef.current);
    }
  }, [team, showTeamPopover]);

  const handleMouseLeave = useCallback(() => {
    hidePopover();
  }, [hidePopover]);

  const handleClick = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    openTeamModal(team);
  }, [team, openTeamModal]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      openTeamModal(team);
    } else if (e.key === 'Escape') {
      hidePopover();
    }
  }, [team, openTeamModal, hidePopover]);

  return (
    <span
      ref={triggerRef}
      className="cursor-pointer h-full"
      role="button"
      tabIndex={0}
      aria-label={`View ${teamName} roster`}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
    >
      {children}
    </span>
  );
};
