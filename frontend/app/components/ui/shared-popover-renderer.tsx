import React, { memo, useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useSharedPopover } from './shared-popover-context';
import { RolePositions } from '~/components/user/positions';
import type { UserType } from '~/components/user/types';
import { AvatarUrl } from '~/index';
import { PlayerModal } from '~/components/player/PlayerModal';
import { TeamModal } from '~/components/team/TeamModal';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '~/components/ui/table';

// Memoized player row for team popover
const TeamMemberRow = memo(({
  member,
  isCaptain,
  onPlayerHover,
  onPlayerLeave,
  onPlayerClick,
}: {
  member: UserType;
  isCaptain: boolean;
  onPlayerHover: (player: UserType, el: HTMLElement) => void;
  onPlayerLeave: () => void;
  onPlayerClick: (player: UserType) => void;
}) => (
  <TableRow>
    <TableCell>
      <div
        className="flex items-center gap-2 cursor-pointer hover:text-primary transition-colors"
        onMouseEnter={(e) => onPlayerHover(member, e.currentTarget)}
        onMouseLeave={onPlayerLeave}
        onClick={() => onPlayerClick(member)}
      >
        <img
          src={AvatarUrl(member)}
          alt={member.username}
          className="w-8 h-8 rounded-full hover:ring-2 hover:ring-primary transition-all"
        />
        <span className="font-medium">
          {member.nickname || member.username}
        </span>
        {isCaptain && (
          <span className="text-xs text-primary">(C)</span>
        )}
      </div>
    </TableCell>
    <TableCell className="text-right">
      {member.mmr?.toLocaleString() || 'N/A'}
    </TableCell>
    <TableCell>
      <RolePositions user={member} />
    </TableCell>
  </TableRow>
));
TeamMemberRow.displayName = 'TeamMemberRow';

// Player popover content
const PlayerPopoverContent: React.FC<{
  player: UserType;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
}> = ({ player, onMouseEnter, onMouseLeave }) => {
  const playerName = player.nickname || player.username || 'Unknown';

  return (
    <div
      className="space-y-2"
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <div className="flex items-center gap-3">
        <img
          src={AvatarUrl(player)}
          alt={`${playerName}'s avatar`}
          className="w-12 h-12 rounded-full"
        />
        <div>
          <p className="font-medium">{playerName}</p>
          {player.mmr && (
            <p className="text-sm text-muted-foreground">
              MMR: {player.mmr.toLocaleString()}
            </p>
          )}
        </div>
      </div>
      <RolePositions user={player} />
      <p className="text-xs text-muted-foreground text-center pt-1">
        Click for full profile
      </p>
    </div>
  );
};

// Team popover content
const TeamPopoverContent: React.FC<{
  team: NonNullable<ReturnType<typeof useSharedPopover>['state']['team']>;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
  onPlayerHover: (player: UserType, el: HTMLElement) => void;
  onPlayerLeave: () => void;
  onPlayerClick: (player: UserType) => void;
}> = ({ team, onMouseEnter, onMouseLeave, onPlayerHover, onPlayerLeave, onPlayerClick }) => {
  const captain = team.captain;
  const teamName = team.name || `${captain?.nickname || captain?.username || 'Unknown'}'s Team`;
  const hasMembers = team.members && team.members.length > 0;

  const avgMMR = hasMembers
    ? Math.round(
        team.members!.reduce((sum: number, m: UserType) => sum + (m.mmr || 0), 0) /
          team.members!.length
      )
    : 0;

  const sortedMembers = hasMembers
    ? [...team.members!].sort((a, b) => {
        if (!a.mmr && !b.mmr) return 0;
        if (!a.mmr) return 1;
        if (!b.mmr) return -1;
        return b.mmr - a.mmr;
      })
    : [];

  return (
    <div onMouseEnter={onMouseEnter} onMouseLeave={onMouseLeave}>
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b">
        <span className="font-medium">{teamName}</span>
        {hasMembers && (
          <span className="text-sm text-muted-foreground">
            {team.members?.length} players | Avg: {avgMMR.toLocaleString()} MMR
          </span>
        )}
      </div>

      {/* Team Table or Empty State */}
      <div className="max-h-80 overflow-y-auto">
        {hasMembers ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Player</TableHead>
                <TableHead className="text-right">MMR</TableHead>
                <TableHead>Positions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sortedMembers.map((member) => (
                <TeamMemberRow
                  key={member.pk}
                  member={member}
                  isCaptain={captain?.pk === member.pk}
                  onPlayerHover={onPlayerHover}
                  onPlayerLeave={onPlayerLeave}
                  onPlayerClick={onPlayerClick}
                />
              ))}
            </TableBody>
          </Table>
        ) : (
          <div className="p-4 text-center text-muted-foreground">
            No players drafted yet
          </div>
        )}
      </div>

      {/* Click hint */}
      <div className="p-2 border-t text-center text-xs text-muted-foreground">
        Click for full view
      </div>
    </div>
  );
};

export const SharedPopoverRenderer: React.FC = () => {
  const {
    state,
    hidePopover,
    showPlayerPopover,
    openPlayerModal,
    openTeamModal,
    playerModalState,
    teamModalState,
    setPlayerModalOpen,
    setTeamModalOpen,
  } = useSharedPopover();

  const popoverRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ top: 0, left: 0 });
  const isHoveringPopoverRef = useRef(false);

  // Calculate position when anchor changes
  useEffect(() => {
    if (state.anchorEl && state.isOpen) {
      const rect = state.anchorEl.getBoundingClientRect();
      const popoverWidth = state.type === 'team' ? 640 : 224;
      const popoverHeight = state.type === 'team' ? 400 : 200;

      let top = rect.bottom + 4;
      let left = rect.left + rect.width / 2 - popoverWidth / 2;

      // Keep within viewport
      if (left < 8) left = 8;
      if (left + popoverWidth > window.innerWidth - 8) {
        left = window.innerWidth - popoverWidth - 8;
      }
      if (top + popoverHeight > window.innerHeight - 8) {
        top = rect.top - popoverHeight - 4;
      }

      setPosition({ top, left });
    }
  }, [state.anchorEl, state.isOpen, state.type]);

  const handlePopoverMouseEnter = useCallback(() => {
    isHoveringPopoverRef.current = true;
  }, []);

  const handlePopoverMouseLeave = useCallback(() => {
    isHoveringPopoverRef.current = false;
    hidePopover();
  }, [hidePopover]);

  const handleClick = useCallback(() => {
    if (state.type === 'player' && state.player) {
      openPlayerModal(state.player);
    } else if (state.type === 'team' && state.team) {
      openTeamModal(state.team);
    }
  }, [state, openPlayerModal, openTeamModal]);

  // Don't render if not open
  if (!state.isOpen) {
    return (
      <>
        {/* Always render modals */}
        {playerModalState.player && (
          <PlayerModal
            player={playerModalState.player}
            open={playerModalState.open}
            onOpenChange={setPlayerModalOpen}
          />
        )}
        {teamModalState.team?.captain && (
          <TeamModal
            team={teamModalState.team}
            captain={teamModalState.team.captain}
            open={teamModalState.open}
            onOpenChange={setTeamModalOpen}
          />
        )}
      </>
    );
  }

  const popoverContent = (
    <>
      <div
        ref={popoverRef}
        className={`fixed z-50 rounded-md border bg-popover text-popover-foreground shadow-md animate-in fade-in-0 zoom-in-95 ${
          state.type === 'team' ? 'w-[640px] p-0' : 'w-56 p-3'
        }`}
        style={{ top: position.top, left: position.left }}
        onClick={handleClick}
        role="tooltip"
      >
        {state.type === 'player' && state.player && (
          <PlayerPopoverContent
            player={state.player}
            onMouseEnter={handlePopoverMouseEnter}
            onMouseLeave={handlePopoverMouseLeave}
          />
        )}
        {state.type === 'team' && state.team && (
          <TeamPopoverContent
            team={state.team}
            onMouseEnter={handlePopoverMouseEnter}
            onMouseLeave={handlePopoverMouseLeave}
            onPlayerHover={showPlayerPopover}
            onPlayerLeave={hidePopover}
            onPlayerClick={openPlayerModal}
          />
        )}
      </div>

      {/* Modals */}
      {playerModalState.player && (
        <PlayerModal
          player={playerModalState.player}
          open={playerModalState.open}
          onOpenChange={setPlayerModalOpen}
        />
      )}
      {teamModalState.team?.captain && (
        <TeamModal
          team={teamModalState.team}
          captain={teamModalState.team.captain}
          open={teamModalState.open}
          onOpenChange={setTeamModalOpen}
        />
      )}
    </>
  );

  return createPortal(popoverContent, document.body);
};
