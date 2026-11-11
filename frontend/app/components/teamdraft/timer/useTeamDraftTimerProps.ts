import { useMemo } from 'react';
import { toast } from 'sonner';
import { pauseTeamDraft, resumeTeamDraft, startTeamDraft } from '~/components/api/draftAPI';
import type { UserType } from '~/index';
import { draftWsSelectors, useDraftWebSocketStore } from '~/store/draftWebSocketStore';
import { useUserStore } from '~/store/userStore';
import { isCaptainOf } from '../isCaptainOf';
import { describeTimerActionError } from '../pickErrors';
import type { ClockTeam, LiveDraftClockBarProps } from './DraftClockBar';
import type { LiveDraftPauseOverlayProps } from './DraftPauseOverlay';

export interface TeamDraftTimerProps {
  showLobby: boolean;
  clockBarProps: LiveDraftClockBarProps;
  pauseOverlayProps: LiveDraftPauseOverlayProps;
}

interface StateTeam {
  pk: number;
  name?: string | null;
  draft_order?: number | null;
  captain?: UserType | null;
}

function runWithToast(action: () => Promise<unknown>, loading: string, success: string, fallback: string): Promise<unknown> {
  const promise = action();
  toast.promise(promise, { loading, success, error: (err: unknown) => describeTimerActionError(err, fallback) });
  return promise.catch(() => undefined);
}

export function useTeamDraftTimerProps(currentUserPk: number | undefined, isStaff: boolean): TeamDraftTimerProps {
  const draftState = useDraftWebSocketStore((s) => s.draftState);
  const captainFresh = useDraftWebSocketStore((s) => s.captainFresh);
  const draftStatus = useDraftWebSocketStore(draftWsSelectors.draftStatus);
  const timerEnabled = useDraftWebSocketStore(draftWsSelectors.timerEnabled);
  const clockArmed = useDraftWebSocketStore(draftWsSelectors.clockArmed);
  const activeRoundPk = useDraftWebSocketStore(draftWsSelectors.activeRoundPk);
  const isActiveCaptainDisconnected = useDraftWebSocketStore(draftWsSelectors.isActiveCaptainDisconnected);
  const userStoreDraftState = useUserStore((s) => s.tournament?.draft?.state);

  return useMemo(() => {
    const ds = draftState;
    const draftPk = ds?.pk;
    const activeRound = ds?.draft_rounds?.find((r) => r.pk === activeRoundPk);
    const activeCaptain = (activeRound?.captain ?? null) as UserType | null;
    const dsTeams = (ds?.tournament?.teams ?? []) as StateTeam[];
    const activeTeamPk = dsTeams.find((t) => t.captain?.pk === activeCaptain?.pk)?.pk ?? null;
    const isCaptain = isCaptainOf(dsTeams, currentUserPk);
    const canControl = isStaff || isCaptain;
    const isMyTurn = currentUserPk != null && activeCaptain?.pk === currentUserPk;
    const teams: ClockTeam[] = [...dsTeams]
      .sort((a, b) => (a.draft_order ?? 0) - (b.draft_order ?? 0))
      .map((t) => ({
        teamPk: t.pk,
        teamName: t.name ?? null,
        captain: t.captain ?? null,
        isConnected: t.captain ? captainFresh[t.captain.pk!] === true : false,
      }));
    const isManualPause = ds?.is_manual_pause === true;

    const act = (fn: (pk: number) => Promise<unknown>, loading: string, success: string, fallback: string) => () =>
      draftPk == null ? Promise.resolve() : runWithToast(() => fn(draftPk), loading, success, fallback);

    return {
      showLobby: (draftStatus ?? userStoreDraftState) === 'pending',
      clockBarProps: {
        timerEnabled,
        clockArmed,
        draftStatus,
        activeTeamPk,
        teams,
        isMyTurn,
        canControl,
        isStaff,
        reserveTotalMs: ds?.draft_options?.reserve_time_ms ?? 0,
        onPause: act(pauseTeamDraft, 'Pausing…', 'Draft paused', 'Failed to pause'),
        onStartClock: act(startTeamDraft, 'Starting clock…', 'Clock started', 'Failed to start clock'),
      },
      pauseOverlayProps: {
        draftStatus,
        isManualPause,
        activeCaptain,
        isActiveCaptainDisconnected,
        canResume: canControl,
        isStaff,
        onResume: act(resumeTeamDraft, 'Resuming…', 'Resuming draft', 'Failed to resume'),
        onPickForCaptain: () =>
          document.querySelector('[data-testid="available-players-section"]')?.scrollIntoView({ behavior: 'smooth' }),
      },
    };
  }, [
    draftState,
    activeRoundPk,
    captainFresh,
    currentUserPk,
    isStaff,
    draftStatus,
    userStoreDraftState,
    timerEnabled,
    clockArmed,
    isActiveCaptainDisconnected,
  ]);
}
