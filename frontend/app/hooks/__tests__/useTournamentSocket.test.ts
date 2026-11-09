import { describe, expect, it, vi } from 'vitest';
import { handleTournamentMessage } from '../useTournamentSocket';

function keys(msg: { type: string; game_id?: number | null }) {
  const queryClient = { invalidateQueries: vi.fn() };
  handleTournamentMessage(queryClient as never, 7, msg);
  return queryClient.invalidateQueries.mock.calls.map((c) => c[0].queryKey);
}

describe('handleTournamentMessage', () => {
  it('ignores initial_events', () => {
    expect(keys({ type: 'initial_events' })).toEqual([]);
  });

  it('refetches the game lobby and the bracket on lobby_event', () => {
    expect(keys({ type: 'lobby_event', game_id: 42 })).toEqual([
      ['tournament', 7],
      ['gameLobby', 42],
      ['bracket', 7],
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
