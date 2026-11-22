// @vitest-environment jsdom
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DisplayName } from '~/index';
import {
  TIE_ROLL_MIN_VISIBLE_MS,
  TieRollPopup,
  liveTieHold,
  tieHoldLeftMs,
  tieRollFrame,
  tieRollKey,
  tieRollTimeline,
} from '../TieRollPopup';
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
    expect(tieRollFrame(100, 2, t)).toEqual({
      round: 0,
      tumbling: true,
      winnerShown: false,
    });
    expect(tieRollFrame(1000, 2, t)).toEqual({
      round: 0,
      tumbling: false,
      winnerShown: false,
    });
    expect(tieRollFrame(1300, 2, t)).toEqual({
      round: 1,
      tumbling: true,
      winnerShown: false,
    });
    expect(tieRollFrame(2400, 2, t)).toEqual({
      round: 1,
      tumbling: false,
      winnerShown: true,
    });
  });
  it('reads the hold left from hold_until, bounded by the full hold', () => {
    const at = (ms: number) => new Date(ms).toISOString();
    expect(tieHoldLeftMs({ ...tie, hold_until: at(3000) }, 1000)).toBe(2000);
    expect(tieHoldLeftMs({ ...tie, hold_until: at(3000) }, 9000)).toBe(0);
    expect(tieHoldLeftMs({ ...tie, hold_until: at(60_000) }, 0)).toBe(5000);
    expect(tieHoldLeftMs({ ...tie, hold_until: undefined }, 0)).toBe(5000);
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
    render(
      <TieRollPopup
        tie={tie}
        teams={teams}
        clockHeld
        onDone={vi.fn()}
        now={now}
      />,
    );
    const popup = screen.getByTestId('tie-roll-popup');
    expect(popup).toHaveTextContent('Tie for pick #3');
    expect(screen.getByTestId('tie-roll-row-1')).toHaveTextContent(
      DisplayName(user(7)),
    );
    expect(screen.getByTestId('tie-roll-row-3')).toHaveTextContent('T3');
    expect(screen.queryByRole('button', { name: /continue/i })).toBeNull();
  });

  it('reveals rolls round by round, marks the dropped team out, then the winner', () => {
    render(
      <TieRollPopup
        tie={tie}
        teams={teams}
        clockHeld
        onDone={vi.fn()}
        now={now}
      />,
    );
    advance(1000);
    expect(screen.getByTestId('tie-roll-die-1')).toHaveAttribute(
      'data-face',
      '6',
    );
    expect(screen.getByTestId('tie-roll-die-3')).toHaveAttribute(
      'data-face',
      '2',
    );
    advance(1100);
    expect(screen.getByTestId('tie-roll-row-3')).toHaveTextContent('out');
    expect(screen.getByTestId('tie-roll-die-2')).toHaveAttribute(
      'data-face',
      '5',
    );
    expect(screen.getByTestId('tie-roll-result')).toHaveTextContent('Rolling');
    advance(400);
    expect(screen.getByTestId('tie-roll-result')).toHaveTextContent(
      `${DisplayName(user(8))} picks next`,
    );
    expect(screen.getByTestId('tie-roll-row-2')).toHaveAttribute(
      'data-winner',
      'true',
    );
  });

  it('closes itself when the hold ends', () => {
    const onDone = vi.fn();
    render(
      <TieRollPopup
        tie={tie}
        teams={teams}
        clockHeld
        onDone={onDone}
        now={now}
      />,
    );
    advance(4900);
    expect(onDone).not.toHaveBeenCalled();
    advance(200);
    expect(onDone).toHaveBeenCalled();
  });

  it('can be hidden early with the close button', () => {
    const onDone = vi.fn();
    render(
      <TieRollPopup
        tie={tie}
        teams={teams}
        clockHeld
        onDone={onDone}
        now={now}
      />,
    );
    fireEvent.click(screen.getByTestId('tie-roll-close'));
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it('shows the clock countdown only when the clock is held', () => {
    const heldTie = { ...tie, hold_until: new Date(5000).toISOString() };
    const { rerender } = render(
      <TieRollPopup
        tie={heldTie}
        teams={teams}
        clockHeld
        onDone={vi.fn()}
        now={now}
        serverNow={now}
      />,
    );
    expect(screen.getByTestId('tie-roll-countdown')).toHaveTextContent(
      'Clock starts in 5s',
    );
    rerender(
      <TieRollPopup
        tie={heldTie}
        teams={teams}
        clockHeld={false}
        onDone={vi.fn()}
        now={now}
      />,
    );
    expect(screen.queryByTestId('tie-roll-countdown')).toBeNull();
  });

  it('falls back to the default hold for payloads without hold_ms', () => {
    const onDone = vi.fn();
    render(
      <TieRollPopup
        tie={{ ...tie, hold_ms: undefined }}
        teams={teams}
        clockHeld
        onDone={onDone}
        now={now}
      />,
    );
    advance(5100);
    expect(onDone).toHaveBeenCalled();
  });

  describe('anchored to the server hold end', () => {
    // Server clock runs 10 s ahead of this browser's performance clock.
    const SERVER_AHEAD = 10_000;
    const serverNow = () => clock + SERVER_AHEAD;
    const heldUntil = (msFromMount: number) =>
      new Date(SERVER_AHEAD + msFromMount).toISOString();

    it('counts down to hold_until, not a fresh hold from mount', () => {
      render(
        <TieRollPopup
          tie={{ ...tie, hold_until: heldUntil(4000) }}
          teams={teams}
          clockHeld
          onDone={vi.fn()}
          now={now}
          serverNow={serverNow}
        />,
      );
      expect(screen.getByTestId('tie-roll-countdown')).toHaveTextContent(
        'Clock starts in 4s',
      );
      advance(2100);
      expect(screen.getByTestId('tie-roll-countdown')).toHaveTextContent(
        'Clock starts in 2s',
      );
    });

    it('closes when the server hold ends', () => {
      const onDone = vi.fn();
      render(
        <TieRollPopup
          tie={{ ...tie, hold_until: heldUntil(4000) }}
          teams={teams}
          clockHeld
          onDone={onDone}
          now={now}
          serverNow={serverNow}
        />,
      );
      advance(3900);
      expect(onDone).not.toHaveBeenCalled();
      advance(200);
      expect(onDone).toHaveBeenCalled();
    });

    it('stays up for the minimum readable time when the hold has nearly run out', () => {
      const onDone = vi.fn();
      render(
        <TieRollPopup
          tie={{ ...tie, hold_until: heldUntil(500) }}
          teams={teams}
          clockHeld
          onDone={onDone}
          now={now}
          serverNow={serverNow}
        />,
      );
      advance(600);
      expect(screen.queryByTestId('tie-roll-countdown')).toBeNull();
      advance(TIE_ROLL_MIN_VISIBLE_MS - 700);
      expect(onDone).not.toHaveBeenCalled();
      advance(200);
      expect(onDone).toHaveBeenCalled();
      expect(screen.getByTestId('tie-roll-result')).toHaveTextContent(
        'picks next',
      );
    });

    it('falls back to hold_ms from mount when hold_until is unreadable', () => {
      const onDone = vi.fn();
      render(
        <TieRollPopup
          tie={{ ...tie, hold_until: 'not a time' }}
          teams={teams}
          clockHeld
          onDone={onDone}
          now={now}
          serverNow={serverNow}
        />,
      );
      advance(4900);
      expect(onDone).not.toHaveBeenCalled();
      advance(200);
      expect(onDone).toHaveBeenCalled();
    });
  });

  describe('following the live hold end', () => {
    const at = (ms: number) => new Date(ms).toISOString();
    const heldTie = { ...tie, hold_until: at(4000) };
    const renderHeld = (onDone: () => void) =>
      render(
        <TieRollPopup
          tie={heldTie}
          teams={teams}
          clockHeld
          onDone={onDone}
          now={now}
          serverNow={now}
          liveHold={{ until: at(4000), paused: false }}
        />,
      );
    const rerenderWith = (
      rerender: (ui: React.ReactElement) => void,
      onDone: () => void,
      liveHold: { until: string | null; paused: boolean },
    ) =>
      rerender(
        <TieRollPopup
          tie={heldTie}
          teams={teams}
          clockHeld
          onDone={onDone}
          now={now}
          serverNow={now}
          liveHold={liveHold}
        />,
      );

    it('shows a paused clock and stays open while the draft is paused', () => {
      const onDone = vi.fn();
      const { rerender } = renderHeld(onDone);
      advance(1000);
      rerenderWith(rerender, onDone, { until: at(4000), paused: true });
      expect(screen.getByTestId('tie-roll-countdown')).toHaveTextContent(
        'Clock paused',
      );
      advance(20_000);
      expect(onDone).not.toHaveBeenCalled();
      expect(screen.getByTestId('tie-roll-countdown')).toHaveTextContent(
        'Clock paused',
      );
    });

    it('counts down to the moved hold end after a resume and closes then', () => {
      const onDone = vi.fn();
      const { rerender } = renderHeld(onDone);
      advance(1000);
      rerenderWith(rerender, onDone, { until: at(4000), paused: true });
      advance(20_000);
      // Resume at 21 s: the server moved the start by the pause plus its countdown.
      rerenderWith(rerender, onDone, { until: at(27_000), paused: false });
      advance(100);
      expect(screen.getByTestId('tie-roll-countdown')).toHaveTextContent(
        'Clock starts in 6s',
      );
      advance(5700);
      expect(onDone).not.toHaveBeenCalled();
      advance(300);
      expect(onDone).toHaveBeenCalled();
    });
  });
});

describe('liveTieHold', () => {
  const round = (pk: number, pick_number: number, started_at: string) => ({
    pk,
    pick_number,
    started_at,
  });
  const draft = {
    state: 'drafting' as const,
    paused_at: null,
    latest_round: 12,
    draft_rounds: [
      round(11, 1, '2026-01-01T00:00:00Z'),
      round(12, 2, '2026-01-01T00:00:09Z'),
    ],
  };
  const tick = {
    active_round_pk: 12,
    active_pick_number: 2,
    round_started_at: '2026-01-01T00:00:30Z',
  };

  it('reads the active round start for the tied pick from the draft state', () => {
    expect(liveTieHold(null, draft, true, 2)).toEqual({
      until: '2026-01-01T00:00:09Z',
      paused: false,
    });
  });
  it('reports a paused draft', () => {
    expect(liveTieHold(null, { ...draft, state: 'paused' }, true, 2)).toEqual({
      until: '2026-01-01T00:00:09Z',
      paused: true,
    });
  });
  it('prefers a newer tick for the same round', () => {
    expect(liveTieHold(tick, draft, true, 2)?.until).toBe(
      '2026-01-01T00:00:30Z',
    );
    expect(liveTieHold(tick, draft, false, 2)?.until).toBe(
      '2026-01-01T00:00:09Z',
    );
  });
  it('has nothing to say once the active round is another pick', () => {
    expect(liveTieHold(null, draft, true, 3)).toBeNull();
    expect(liveTieHold(null, null, true, 2)).toBeNull();
  });
});
