import React, {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from 'react';
import { createPortal } from 'react-dom';
import { GAME_SHORT_LABEL, toGameType } from '~/components/game/constants';
import { PlayerLeagueSummary } from '~/components/player/PlayerLeagueSummary';
import { PlayerModal } from '~/components/player/PlayerModal';
import { TeamModal } from '~/components/team/TeamModal';
import { TeamPopoverContent } from '~/components/team/TeamPopoverContent';
import { RolePositions } from '~/components/user/positions';
import type { UserType } from '~/components/user/types';
import { UserAvatar } from '~/components/user/UserAvatar';
import { useGameType } from '~/hooks/useGameType';
import { useLeagueStore } from '~/store/leagueStore';
import { useOrgStore } from '~/store/orgStore';
import { useUserStore } from '~/store/userStore';
import { useSharedPopover } from './shared-popover-context';

// Player popover content
const PlayerPopoverContent: React.FC<{
  player: UserType;
  statsLeagueId?: number | null;
}> = ({ player, statsLeagueId }) => {
  const gameType = useGameType();
  const playerName = player.nickname || player.username || 'Unknown';
  const mmrGame = gameType ?? toGameType(player.mmr_game_type);

  return (
    <div className="flex flex-col gap-3 w-full overflow-hidden">
      {/* Header: Avatar + Name/MMR */}
      <div className="flex items-center gap-4 min-w-0">
        <UserAvatar user={player} size="xl" className="shrink-0" />
        <div className="min-w-0 flex-1 overflow-hidden">
          <p className="font-semibold text-foreground text-lg truncate">
            {playerName}
          </p>
          {player.mmr && (
            <p
              className="text-sm text-foreground/70"
              data-testid="player-popover-mmr"
            >
              {GAME_SHORT_LABEL[mmrGame]} {player.mmr.toLocaleString()}
            </p>
          )}
        </div>
      </div>
      {/* Positions - pt-1 pl-1 accommodates absolute positioned rank badges */}
      <div className="w-full pt-1 pl-1">
        <div className="flex flex-wrap gap-1">
          <RolePositions user={player} disableTooltips />
        </div>
      </div>
      {statsLeagueId != null && player.pk != null && (
        <PlayerLeagueSummary
          leaguePk={statsLeagueId}
          userId={player.pk}
          compact
        />
      )}
      <p className="text-xs text-foreground/60 text-center">
        Click for full profile
      </p>
    </div>
  );
};

export const SharedPopoverRenderer: React.FC = () => {
  const {
    state,
    scheduleHidePopover,
    cancelHidePopover,
    showPlayerPopover,
    openPlayerModal,
    openTeamModal,
    playerModalState,
    teamModalState,
    setPlayerModalOpen,
    setTeamModalOpen,
  } = useSharedPopover();

  const currentOrg = useOrgStore((s) => s.currentOrg);
  const currentLeague = useLeagueStore((s) => s.currentLeague);
  const snapshotTeam = teamModalState.team;
  const liveTeam = useUserStore((s) =>
    snapshotTeam?.pk != null
      ? s.tournament?.teams?.find((t) => t.pk === snapshotTeam.pk)
      : undefined,
  );
  const teamModalTeam = liveTeam ?? snapshotTeam;

  const popoverRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ top: 0, left: 0 });
  const isHoveringPopoverRef = useRef(false);

  // Place the card from its measured size; re-place when it resizes (e.g. league stats load).
  const placePopover = useCallback(() => {
    if (state.anchorEl && state.isOpen) {
      const rect = state.anchorEl.getBoundingClientRect();
      const popoverWidth = state.type === 'team' ? 640 : 400;
      const popoverHeight =
        popoverRef.current?.offsetHeight || (state.type === 'team' ? 400 : 280);

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
      if (top < 8) top = 8;

      setPosition((prev) =>
        prev.top === top && prev.left === left ? prev : { top, left },
      );
    }
  }, [state.anchorEl, state.isOpen, state.type]);

  useLayoutEffect(placePopover, [placePopover]);

  useEffect(() => {
    const el = popoverRef.current;
    if (!state.isOpen || !el || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(placePopover);
    observer.observe(el);
    return () => observer.disconnect();
  }, [state.isOpen, placePopover]);

  const handlePopoverMouseEnter = useCallback(() => {
    isHoveringPopoverRef.current = true;
    cancelHidePopover();
  }, [cancelHidePopover]);

  const handlePopoverMouseLeave = useCallback(() => {
    isHoveringPopoverRef.current = false;
    scheduleHidePopover();
  }, [scheduleHidePopover]);

  const handleClick = useCallback(() => {
    if (state.type === 'player' && state.player) {
      openPlayerModal(state.player, {
        organizationId: currentOrg?.pk,
        leagueId: currentLeague?.pk,
        statsLeagueId: state.context?.statsLeagueId,
      });
    } else if (state.type === 'team' && state.team) {
      openTeamModal(state.team);
    }
  }, [
    state,
    openPlayerModal,
    openTeamModal,
    currentOrg?.pk,
    currentLeague?.pk,
  ]);

  const modals = (
    <>
      {playerModalState.player && (
        <PlayerModal
          player={playerModalState.player}
          open={playerModalState.open}
          onOpenChange={setPlayerModalOpen}
          leagueId={playerModalState.context?.leagueId}
          organizationId={playerModalState.context?.organizationId}
        />
      )}
      {teamModalTeam && (
        <TeamModal
          team={teamModalTeam}
          open={teamModalState.open}
          onOpenChange={setTeamModalOpen}
        />
      )}
    </>
  );

  const popoverContent = (
    <div
      ref={popoverRef}
      className={`fixed z-50 rounded-md border bg-popover text-popover-foreground shadow-md animate-in fade-in-0 zoom-in-95 ${
        state.type === 'team' ? 'w-[640px] p-0' : 'w-[400px] p-4'
      }`}
      style={{ top: position.top, left: position.left }}
      onClick={handleClick}
      onMouseEnter={handlePopoverMouseEnter}
      onMouseLeave={handlePopoverMouseLeave}
      role="tooltip"
    >
      {state.type === 'player' && state.player && (
        <PlayerPopoverContent
          player={state.player}
          statsLeagueId={state.context?.statsLeagueId}
        />
      )}
      {state.type === 'team' && state.team && (
        <TeamPopoverContent
          team={state.team}
          onPlayerHover={showPlayerPopover}
          onPlayerLeave={scheduleHidePopover}
          onPlayerClick={openPlayerModal}
        />
      )}
    </div>
  );

  // Modals keep one tree position so opening a popover never remounts them.
  return (
    <>
      {modals}
      {state.isOpen && createPortal(popoverContent, document.body)}
    </>
  );
};
