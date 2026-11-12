// @vitest-environment jsdom
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DisplayName } from '~/index';
import { TieRollPopup, tieRollFrame, tieRollKey, tieRollTimeline } from '../TieRollPopup';
import type { TieResolution } from '../types';
import { user } from './fixtures';

const tie: TieResolution = {
  pick_number: 3,
  hold_ms: 5000,
  winner_id: 2,
  tied_teams: [
    { id: 1, name: 'T1', mmr: 0 },
    { id: 2, name: 'T2', mmr: 0 },
    { id: 3, name: 'T3', mmr: 0 },
  ],
  roll_rounds: [
    [
      { team_id: 1, roll: 6 },
      { team_id: 2, roll: 6 },
      { team_id: 3, roll: 2 },
    ],
    [
      { team_id: 1, roll: 1 },
      { team_id: 2, roll: 5 },
    ],
  ],
};
const teams = [
  { id: 1, captain: user(7) },
  { id: 2, captain: user(8) },
  { id: 3, captain: null },
];

describe('tieRollTimeline / tieRollFrame', () => {
  it('fits the rounds and a winner linger inside the hold', () => {
    const t = tieRollTimeline(2, 5000);
    expect(t.totalMs).toBe(5000);
    expect(t.roundMs).toBe(1200);
    expect(t.winnerAtMs).toBe(2400);
  });
  it('stretches past a short hold rather than skipping rounds', () => {
    const t = tieRollTimeline(10, 3000);
    expect(t.roundMs).toBe(500);
    expect(t.totalMs).toBe(6500);
  });
  it('tumbles early in each round, then reveals, then shows the winner', () => {
    const t = tieRollTimeline(2, 5000);
    expect(tieRollFrame(100, 2, t)).toEqual({ round: 0, tumbling: true, winnerShown: false });
    expect(tieRollFrame(1000, 2, t)).toEqual({ round: 0, tumbling: false, winnerShown: false });
    expect(tieRollFrame(1300, 2, t)).toEqual({ round: 1, tumbling: true, winnerShown: false });
    expect(tieRollFrame(2400, 2, t)).toEqual({ round: 1, tumbling: false, winnerShown: true });
  });
  it('keys the same roll identically and different picks differently', () => {
    expect(tieRollKey(tie)).toBe(tieRollKey({ ...tie }));
    expect(tieRollKey(tie)).not.toBe(tieRollKey({ ...tie, pick_number: 4 }));
  });
});

describe('TieRollPopup', () => {
  let clock = 0;
  const now = () => clock;
  const advance = (ms: number) => {
    act(() => {
      clock += ms;
      vi.advanceTimersByTime(ms);
    });
  };

  beforeEach(() => {
    clock = 0;
    vi.useFakeTimers();
  });
  afterEach(() => vi.useRealTimers());

  it('names captains, says which pick, and has no Continue button', () => {
    render(<TieRollPopup tie={tie} teams={teams} clockHeld onDone={vi.fn()} now={now} />);
    const popup = screen.getByTestId('tie-roll-popup');
    expect(popup).toHaveTextContent('Tie for pick #3');
    expect(screen.getByTestId('tie-roll-row-1')).toHaveTextContent(DisplayName(user(7)));
    expect(screen.getByTestId('tie-roll-row-3')).toHaveTextContent('T3');
    expect(screen.queryByRole('button', { name: /continue/i })).toBeNull();
  });

  it('reveals rolls round by round, marks the dropped team out, then the winner', () => {
    render(<TieRollPopup tie={tie} teams={teams} clockHeld onDone={vi.fn()} now={now} />);
    advance(1000);
    expect(screen.getByTestId('tie-roll-die-1')).toHaveAttribute('data-face', '6');
    expect(screen.getByTestId('tie-roll-die-3')).toHaveAttribute('data-face', '2');
    advance(1100);
    expect(screen.getByTestId('tie-roll-row-3')).toHaveTextContent('out');
    expect(screen.getByTestId('tie-roll-die-2')).toHaveAttribute('data-face', '5');
    expect(screen.getByTestId('tie-roll-result')).toHaveTextContent('Rolling');
    advance(400);
    expect(screen.getByTestId('tie-roll-result')).toHaveTextContent(`${DisplayName(user(8))} picks next`);
    expect(screen.getByTestId('tie-roll-row-2')).toHaveAttribute('data-winner', 'true');
  });

  it('closes itself when the hold ends', () => {
    const onDone = vi.fn();
    render(<TieRollPopup tie={tie} teams={teams} clockHeld onDone={onDone} now={now} />);
    advance(4900);
    expect(onDone).not.toHaveBeenCalled();
    advance(200);
    expect(onDone).toHaveBeenCalled();
  });

  it('can be hidden early with the close button', () => {
    const onDone = vi.fn();
    render(<TieRollPopup tie={tie} teams={teams} clockHeld onDone={onDone} now={now} />);
    fireEvent.click(screen.getByTestId('tie-roll-close'));
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it('shows the clock countdown only when the clock is held', () => {
    const { rerender } = render(<TieRollPopup tie={tie} teams={teams} clockHeld onDone={vi.fn()} now={now} />);
    expect(screen.getByTestId('tie-roll-countdown')).toHaveTextContent('Clock starts in 5s');
    rerender(<TieRollPopup tie={tie} teams={teams} clockHeld={false} onDone={vi.fn()} now={now} />);
    expect(screen.queryByTestId('tie-roll-countdown')).toBeNull();
  });

  it('falls back to the default hold for payloads without hold_ms', () => {
    const onDone = vi.fn();
    render(<TieRollPopup tie={{ ...tie, hold_ms: undefined }} teams={teams} clockHeld onDone={onDone} now={now} />);
    advance(5100);
    expect(onDone).toHaveBeenCalled();
  });
});
