import { describe, expect, it, vi } from 'vitest';
import { handleTournamentMessage } from '../useTournamentSocket';

type Msg = { type: string; game_id?: number | null; state?: string | null };

function keys(msg: Msg, bracket?: unknown) {
  const queryClient = {
    invalidateQueries: vi.fn(),
    getQueryData: vi.fn((key: unknown[]) =>
      key[0] === 'bracket' && key[1] === 7 ? bracket : undefined,
    ),
  };
  handleTournamentMessage(queryClient as never, 7, msg);
  return queryClient.invalidateQueries.mock.calls.map((c) => c[0].queryKey);
}

const bracket = (lobbyState: string | null) => ({
  tournamentId: 7,
  matches: [{ pk: 42, lobby_state: lobbyState }],
});

describe('handleTournamentMessage', () => {
  it('ignores initial_events', () => {
    expect(keys({ type: 'initial_events' })).toEqual([]);
  });

  it('refetches the game lobby and the bracket when the lobby state changed', () => {
    expect(keys({ type: 'lobby_event', game_id: 42, state: 'ready' }, bracket('waiting'))).toEqual([
      ['gameLobby', 42],
      ['bracket', 7],
    ]);
  });

  it('refetches the bracket for a game that had no lobby yet', () => {
    expect(keys({ type: 'lobby_event', game_id: 42, state: 'requested' }, bracket(null))).toEqual([
      ['gameLobby', 42],
      ['bracket', 7],
    ]);
  });

  it('refetches only the game lobby when the lobby state did not change', () => {
    // player_invited, player_joined, ... keep the state: no bracket or
    // tournament refetch for every spectator.
    expect(keys({ type: 'lobby_event', game_id: 42, state: 'waiting' }, bracket('waiting'))).toEqual([
      ['gameLobby', 42],
    ]);
  });

  it('does not refetch an uncached bracket on lobby_event', () => {
    expect(keys({ type: 'lobby_event', game_id: 42, state: 'ready' })).toEqual([['gameLobby', 42]]);
    expect(keys({ type: 'lobby_event', game_id: 99, state: 'ready' }, bracket('waiting'))).toEqual([
      ['gameLobby', 99],
    ]);
  });

  it('refetches the bracket on bracket_update', () => {
    expect(keys({ type: 'bracket_update', game_id: 42 })).toEqual([
      ['tournament', 7],
      ['bracket', 7],
    ]);
  });

  it('refetches only the tournament for other events', () => {
    expect(keys({ type: 'draft_event' })).toEqual([['tournament', 7]]);
  });
});
