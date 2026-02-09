import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { getWebSocketManager } from '~/lib/websocket';
import { getLogger } from '~/lib/logger';

const log = getLogger('useTournamentSocket');

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

    const unsub = manager.subscribe(connId, (message) => {
      const msg = message as { type: string };
      log.debug('Tournament WS event', msg.type);

      // Skip initial_events — no state change on connect
      if (msg.type === 'initial_events') return;

      // Invalidate tournament query on any event
      queryClient.invalidateQueries({ queryKey: ['tournament', tournamentId] });

      // Future: when backend sends bracket_update events, also invalidate bracket
      if (msg.type === 'bracket_update') {
        queryClient.invalidateQueries({ queryKey: ['bracket', tournamentId] });
      }
    });

    return () => unsub(); // auto-disconnects when no subscribers remain
  }, [tournamentId, queryClient]);
}
