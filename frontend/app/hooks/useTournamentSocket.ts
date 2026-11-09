import { useEffect } from 'react';
import { useQueryClient, type QueryClient } from '@tanstack/react-query';
import { getWebSocketManager } from '~/lib/websocket';
import { getLogger } from '~/lib/logger';

const log = getLogger('useTournamentSocket');

interface TournamentSocketMessage {
  type: string;
  game_id?: number | null;
}

/**
 * Invalidates the TanStack Query caches a TournamentConsumer message affects.
 * Exported for tests.
 */
export function handleTournamentMessage(
  queryClient: Pick<QueryClient, 'invalidateQueries'>,
  tournamentId: number,
  msg: TournamentSocketMessage,
) {
  // Skip initial_events — no state change on connect
  if (msg.type === 'initial_events') return;

  // Invalidate tournament query on any event
  queryClient.invalidateQueries({ queryKey: ['tournament', tournamentId] });

  if (msg.type === 'bracket_update') {
    queryClient.invalidateQueries({ queryKey: ['bracket', tournamentId] });
  }

  // A game's dota_lobby lobby changed: refetch it, and the bracket for the
  // lobby state dot.
  if (msg.type === 'lobby_event') {
    if (msg.game_id) {
      queryClient.invalidateQueries({ queryKey: ['gameLobby', msg.game_id] });
    }
    queryClient.invalidateQueries({ queryKey: ['bracket', tournamentId] });
  }
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

    const unsub = manager.subscribe(connId, (message) => {
      const msg = message as TournamentSocketMessage;
      log.debug('Tournament WS event', msg.type);
      handleTournamentMessage(queryClient, tournamentId, msg);
    });

    return () => unsub(); // auto-disconnects when no subscribers remain
  }, [tournamentId, queryClient]);
}
