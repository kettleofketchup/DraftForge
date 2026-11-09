import { useEffect } from 'react';
import { useQueryClient, type QueryClient } from '@tanstack/react-query';
import { getWebSocketManager } from '~/lib/websocket';
import { getLogger } from '~/lib/logger';
import type { BracketResponseDTO } from '~/components/bracket/schemas';

const log = getLogger('useTournamentSocket');

interface TournamentSocketMessage {
  type: string;
  game_id?: number | null;
  state?: string | null;
}

/**
 * The lobby state the cached bracket shows for a game: a string, `null` for
 * no lobby, or `undefined` when the bracket (or the game) is not cached.
 */
function cachedLobbyState(
  queryClient: Pick<QueryClient, 'getQueryData'>,
  tournamentId: number,
  gameId: number,
): string | null | undefined {
  const bracket = queryClient.getQueryData<BracketResponseDTO>(['bracket', tournamentId]);
  const match = bracket?.matches.find((m) => m.pk === gameId);
  return match ? (match.lobby_state ?? null) : undefined;
}

/**
 * Invalidates the TanStack Query caches a TournamentConsumer message affects.
 * Exported for tests.
 */
export function handleTournamentMessage(
  queryClient: Pick<QueryClient, 'invalidateQueries' | 'getQueryData'>,
  tournamentId: number,
  msg: TournamentSocketMessage,
) {
  // Skip initial_events — no state change on connect
  if (msg.type === 'initial_events') return;

  // A game's dota_lobby lobby changed: refetch that lobby. Most lobby events
  // (invites, joins, seats, ready) leave its state alone, and the tournament
  // holds no lobby data, so the bracket is refetched only when the state
  // its lobby dot shows has changed. Game changes come as bracket_update.
  if (msg.type === 'lobby_event') {
    if (!msg.game_id) return;
    queryClient.invalidateQueries({ queryKey: ['gameLobby', msg.game_id] });
    const shown = cachedLobbyState(queryClient, tournamentId, msg.game_id);
    if (shown !== undefined && shown !== (msg.state ?? null)) {
      queryClient.invalidateQueries({ queryKey: ['bracket', tournamentId] });
    }
    return;
  }

  // Invalidate tournament query on any other event
  queryClient.invalidateQueries({ queryKey: ['tournament', tournamentId] });

  if (msg.type === 'bracket_update') {
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
