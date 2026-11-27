import { beforeEach, describe, expect, it } from 'vitest';
import type { BracketMatch } from '~/components/bracket/types';
import type { TeamType } from '~/components/tournament/types';
import { useBracketStore } from './bracketStore';

const teamA = { pk: 1, name: 'Team A' } as unknown as TeamType;
const teamB = { pk: 2, name: 'Team B' } as unknown as TeamType;

function baseMatch(overrides: Partial<BracketMatch> = {}): BracketMatch {
  return {
    id: 'gf-1-0',
    gameId: 10,
    round: 1,
    position: 0,
    bracketType: 'grand_finals',
    eliminationType: 'double',
    radiantTeam: teamA,
    direTeam: teamB,
    status: 'pending',
    swissRecordWins: 0,
    swissRecordLosses: 0,
    ...overrides,
  };
}

describe('useBracketStore.unsetMatchWinner', () => {
  beforeEach(() => {
    useBracketStore.setState({
      matches: [],
      nodes: [],
      edges: [],
      isDirty: false,
      isVirtual: true,
    });
  });

  it('clears winner and downstream slot when winner is set', () => {
    const downstream = baseMatch({
      id: 'gf-1-1',
      gameId: 11,
      bracketType: 'grand_finals',
      radiantTeam: teamA,
      direTeam: undefined,
      status: 'pending',
    });
    const match = baseMatch({
      winner: 'radiant',
      status: 'completed',
      nextMatchId: 'gf-1-1',
      nextMatchSlot: 'radiant',
    });
    useBracketStore.setState({ matches: [match, downstream], isDirty: false });

    useBracketStore.getState().unsetMatchWinner(match.id);

    const next = useBracketStore.getState();
    const updated = next.matches.find((m) => m.id === match.id)!;
    expect(updated.winner).toBeUndefined();
    expect(updated.status).toBe('pending');
    // Winning team is removed from the downstream slot it had been advanced into.
    const downstreamAfter = next.matches.find((m) => m.id === 'gf-1-1')!;
    expect(downstreamAfter.radiantTeam).toBeUndefined();
    expect(next.isDirty).toBe(true);
  });

  it('recovers a stuck row (status=completed, winner=undefined) by clearing only the status', () => {
    // Models the production bug: backend's winning_team FK no longer matches
    // either radiant_team or dire_team, so mapApiMatchToMatch can't derive
    // a winner. Without recovery, the Set Winner buttons are hidden
    // (status === 'completed') AND the Unset Winner button was gated on
    // winner being truthy — admin gets stuck. The recovery path resets
    // status alone so the Set Winner buttons reappear.
    const stuck = baseMatch({
      winner: undefined,
      status: 'completed',
      nextMatchId: undefined,
      nextMatchSlot: undefined,
    });
    useBracketStore.setState({ matches: [stuck], isDirty: false });

    useBracketStore.getState().unsetMatchWinner(stuck.id);

    const updated = useBracketStore
      .getState()
      .matches.find((m) => m.id === stuck.id)!;
    expect(updated.status).toBe('pending');
    expect(updated.winner).toBeUndefined();
    expect(useBracketStore.getState().isDirty).toBe(true);
  });

  it('is a no-op when the row is already pending and has no winner', () => {
    const idle = baseMatch({ winner: undefined, status: 'pending' });
    useBracketStore.setState({ matches: [idle], isDirty: false });

    useBracketStore.getState().unsetMatchWinner(idle.id);

    // Nothing changed: no winner to clear and no completed status to recover.
    expect(useBracketStore.getState().isDirty).toBe(false);
  });

  it('is a no-op when the match id does not exist in the store', () => {
    useBracketStore.setState({ matches: [], isDirty: false });
    useBracketStore.getState().unsetMatchWinner('does-not-exist');
    expect(useBracketStore.getState().isDirty).toBe(false);
  });
});

describe('useBracketStore structural edits (issue #963)', () => {
  beforeEach(() => {
    useBracketStore.setState({
      matches: [
        baseMatch({
          id: 'w-1-0',
          bracketType: 'winners',
          nextMatchId: 'w-2-0',
          nextMatchSlot: 'radiant',
        }),
        baseMatch({
          id: 'w-2-0',
          gameId: 11,
          bracketType: 'winners',
          round: 2,
          radiantTeam: undefined,
          direTeam: undefined,
        }),
      ],
      isDirty: false,
      hasStructuralEdits: false,
    });
  });

  it('a winner and its advancement are not structural edits', () => {
    const store = useBracketStore.getState();
    store.setMatchWinner('w-1-0', 'radiant');
    store.advanceWinner('w-1-0');

    const next = useBracketStore.getState();
    expect(next.matches.find((m) => m.id === 'w-2-0')!.radiantTeam).toBe(teamA);
    expect(next.isDirty).toBe(true);
    expect(next.hasStructuralEdits).toBe(false);
  });

  it('placing a team by hand is a structural edit', () => {
    useBracketStore.getState().assignTeamToSlot('w-2-0', 'dire', teamB);

    expect(useBracketStore.getState().hasStructuralEdits).toBe(true);
  });
});
