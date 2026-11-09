import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { getWebSocketManager } from '~/lib/websocket';
import { getLogger } from '~/lib/logger';
import { useDraftWebSocketStore } from '~/store/draftWebSocketStore';

const log = getLogger('useTournamentSocket');

/**
 * Throttle window: the first event schedules one refetch this long after it,
 * and events inside the window share it (a timeout sends up to five).
 */
export const TOURNAMENT_REFETCH_WINDOW_MS = 300;

/** Events whose effect reaches past the draft state (the draft ends). */
const TOURNAMENT_LEVEL_EVENTS = new Set(['draft_completed']);

type TournamentSocketMessage = {
  type: string;
  event?: { event_type?: string } | null;
  draft_state?: { pk?: number } | null;
};

/**
 * True when the open draft socket applies everything this event changed: its
 * draft_state carries the draft and the tournament's teams, and picks, pauses
 * and clock events change nothing else on the tournament.
 */
function appliedByDraftSocket(msg: TournamentSocketMessage): boolean {
  if (msg.type !== 'draft_event' || !msg.draft_state?.pk) return false;
  if (TOURNAMENT_LEVEL_EVENTS.has(msg.event?.event_type ?? '')) return false;
  const ws = useDraftWebSocketStore.getState();
  return ws._currentDraftId === msg.draft_state.pk && ws.status === 'connected';
}

/**
 * Connects to the TournamentConsumer WebSocket and invalidates
 * TanStack Query cache on server events. The refetchInterval on
 * each query acts as a fallback if the WebSocket disconnects.
 */
export function useTournamentSocket(tournamentId: number | null) {
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!tournamentId) return;

    const manager = getWebSocketManager();
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${window.location.host}/api/tournament/${tournamentId}/`;
    const connId = manager.connect(url);
    let timer: ReturnType<typeof setTimeout> | null = null;

    const unsub = manager.subscribe(connId, (message) => {
      const msg = message as TournamentSocketMessage;
      log.debug('Tournament WS event', msg.type);

      // Skip initial_events — no state change on connect
      if (msg.type === 'initial_events') return;

      if (msg.type === 'bracket_update') {
        queryClient.invalidateQueries({ queryKey: ['bracket', tournamentId] });
      }

      if (appliedByDraftSocket(msg)) return;
      if (timer !== null) return;
      timer = setTimeout(() => {
        timer = null;
        queryClient.invalidateQueries({ queryKey: ['tournament', tournamentId] });
      }, TOURNAMENT_REFETCH_WINDOW_MS);
    });

    return () => {
      if (timer !== null) clearTimeout(timer);
      unsub(); // auto-disconnects when no subscribers remain
    };
  }, [tournamentId, queryClient]);
}
