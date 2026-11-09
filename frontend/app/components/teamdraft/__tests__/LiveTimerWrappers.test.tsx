// @vitest-environment jsdom
import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useDraftWebSocketStore } from '~/store/draftWebSocketStore';
import { LiveDraftClockBar } from '../timer/DraftClockBar';
import { LiveDraftPauseOverlay } from '../timer/DraftPauseOverlay';
import { T0, user } from './fixtures';

const draft = (o: Record<string, unknown> = {}) => ({
  pk: 1,
  state: 'drafting',
  clock_armed: true,
  latest_round: 21,
  draft_rounds: [{ pk: 21, pick_number: 1, captain: user(7), started_at: new Date(T0 - 5_000).toISOString(), grace_time_ms: 20_000 }],
  tournament: { teams: [{ pk: 1, captain: user(7), draft_reserve_ms: 30_000 }] },
  ...o,
});

const clockProps = {
  timerEnabled: true,
  clockArmed: true,
  draftStatus: 'drafting' as const,
  activeTeamPk: 1,
  teams: [{ teamPk: 1, teamName: 'T1', captain: user(7), isConnected: true }],
  isMyTurn: false,
  canControl: false,
  isStaff: false,
  reserveTotalMs: 30_000,
  onPause: vi.fn(),
  onStartClock: vi.fn(),
};

const overlayProps = {
  isManualPause: false,
  activeCaptain: user(7),
  isActiveCaptainDisconnected: false,
  canResume: true,
  isStaff: false,
  onResume: vi.fn(),
  onPickForCaptain: vi.fn(),
};

describe('live timer wrappers', () => {
  beforeEach(() => {
    useDraftWebSocketStore.getState().reset();
    vi.useFakeTimers();
    vi.setSystemTime(T0);
  });
  afterEach(() => vi.useRealTimers());

  it('LiveDraftClockBar derives and ticks the countdown from the store', () => {
    useDraftWebSocketStore.setState({ draftState: draft() as never, tick: null });
    render(<LiveDraftClockBar {...clockProps} />);
    expect(screen.getByTestId('draft-clock-grace')).toHaveTextContent('0:15');
    act(() => {
      vi.advanceTimersByTime(2_000);
    });
    expect(screen.getByTestId('draft-clock-grace')).toHaveTextContent('0:13');
  });

  it('LiveDraftPauseOverlay derives the resuming countdown from the store', () => {
    useDraftWebSocketStore.setState({
      draftState: draft({ state: 'resuming', resuming_until: new Date(T0 + 2_400).toISOString() }) as never,
      tick: null,
    });
    render(<LiveDraftPauseOverlay {...overlayProps} draftStatus="resuming" />);
    expect(screen.getByTestId('draft-resuming-countdown')).toHaveTextContent('Resuming in 3');
  });
});
