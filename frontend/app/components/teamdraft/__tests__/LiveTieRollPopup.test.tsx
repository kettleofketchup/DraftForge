// @vitest-environment jsdom
import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useDraftWebSocketStore } from '~/store/draftWebSocketStore';
import { LiveTieRollPopup } from '../LiveTieRollPopup';
import type { TieResolution } from '../types';
import { T0, user } from './fixtures';

const holdUntil = new Date(T0 + 4_000).toISOString();

const tie: TieResolution = {
  pick_number: 2,
  hold_ms: 5000,
  hold_until: holdUntil,
  winner_id: 2,
  tied_teams: [
    { id: 1, name: 'T1', mmr: 0 },
    { id: 2, name: 'T2', mmr: 0 },
  ],
  roll_rounds: [
    [
      { team_id: 1, roll: 2 },
      { team_id: 2, roll: 5 },
    ],
  ],
};

const draft = (state: string, startedAt: string) => ({
  pk: 1,
  state,
  latest_round: 22,
  draft_rounds: [
    { pk: 21, pick_number: 1, captain: user(7), started_at: null },
    { pk: 22, pick_number: 2, captain: user(8), started_at: startedAt },
  ],
});

const setDraft = (state: string, startedAt: string) =>
  act(() => {
    useDraftWebSocketStore.setState({
      draftState: draft(state, startedAt) as never,
      _draftStateSeq: 1,
    });
  });

describe('LiveTieRollPopup', () => {
  beforeEach(() => {
    useDraftWebSocketStore.getState().reset();
    vi.useFakeTimers();
    vi.setSystemTime(T0);
  });
  afterEach(() => vi.useRealTimers());

  it('shows the paused clock from the live draft state and follows the resumed start', () => {
    const onDone = vi.fn();
    setDraft('drafting', holdUntil);
    render(<LiveTieRollPopup tie={tie} teams={[]} clockHeld onDone={onDone} />);
    expect(screen.getByTestId('tie-roll-countdown')).toHaveTextContent(
      'Clock starts in 4s',
    );

    setDraft('paused', holdUntil);
    act(() => vi.advanceTimersByTime(30_000));
    expect(screen.getByTestId('tie-roll-countdown')).toHaveTextContent(
      'Clock paused',
    );
    expect(onDone).not.toHaveBeenCalled();

    setDraft('resuming', new Date(T0 + 40_000).toISOString());
    act(() => vi.advanceTimersByTime(100));
    expect(screen.getByTestId('tie-roll-countdown')).toHaveTextContent(
      'Clock starts in 10s',
    );
    act(() => vi.advanceTimersByTime(9_800));
    expect(onDone).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(300));
    expect(onDone).toHaveBeenCalled();
  });
});
