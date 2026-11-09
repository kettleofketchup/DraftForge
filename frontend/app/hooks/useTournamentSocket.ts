import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { getWebSocketManager } from '~/lib/websocket';
import { getLogger } from '~/lib/logger';
import { useDraftWebSocketStore } from '~/store/draftWebSocketStore';

const log = getLogger('useTournamentSocket');

/** A burst of events (a timeout fires up to five) costs one refetch. */
export const TOURNAMENT_REFETCH_DEBOUNCE_MS = 300;

type TournamentSocketMessage = {
  type: string;
  draft_state?: { pk?: number } | null;
};

/** The open draft socket already applies this event's draft_state to the stores. */
function appliedByDraftSocket(msg: TournamentSocketMessage): boolean {
  if (msg.type !== 'draft_event' || !msg.draft_state?.pk) return false;
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
      }, TOURNAMENT_REFETCH_DEBOUNCE_MS);
    });

    return () => {
      if (timer !== null) clearTimeout(timer);
      unsub(); // auto-disconnects when no subscribers remain
    };
  }, [tournamentId, queryClient]);
}
