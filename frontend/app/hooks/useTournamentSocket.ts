import { useEffect } from 'react';
import { useQueryClient, type QueryClient } from '@tanstack/react-query';
import { getWebSocketManager } from '~/lib/websocket';
import { getLogger } from '~/lib/logger';
import type { BracketResponseDTO } from '~/components/bracket/schemas';
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
  game_id?: number | null;
  state?: string | null;
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
 * `refetchTournament` refetches the tournament; the hook passes a throttled
 * one, and it defaults to an immediate invalidation. Exported for tests.
 */
export function handleTournamentMessage(
  queryClient: Pick<QueryClient, 'invalidateQueries' | 'getQueryData'>,
  tournamentId: number,
  msg: TournamentSocketMessage,
  refetchTournament: () => void = () => {
    queryClient.invalidateQueries({ queryKey: ['tournament', tournamentId] });
  },
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

  if (msg.type === 'bracket_update') {
    queryClient.invalidateQueries({ queryKey: ['bracket', tournamentId] });
  }

  if (appliedByDraftSocket(msg)) return;
  refetchTournament();
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

    const refetchTournament = () => {
      if (timer !== null) return;
      timer = setTimeout(() => {
        timer = null;
        queryClient.invalidateQueries({ queryKey: ['tournament', tournamentId] });
      }, TOURNAMENT_REFETCH_WINDOW_MS);
    };

    const unsub = manager.subscribe(connId, (message) => {
      const msg = message as TournamentSocketMessage;
      log.debug('Tournament WS event', msg.type);
      handleTournamentMessage(queryClient, tournamentId, msg, refetchTournament);
    });

    return () => {
      if (timer !== null) clearTimeout(timer);
      unsub(); // auto-disconnects when no subscribers remain
    };
  }, [tournamentId, queryClient]);
}
