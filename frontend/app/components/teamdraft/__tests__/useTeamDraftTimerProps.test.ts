// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useDraftWebSocketStore } from '~/store/draftWebSocketStore';
import { useTeamDraftTimerProps } from '../timer/useTeamDraftTimerProps';
import { T0, user } from './fixtures';

const ds = (o: Record<string, unknown> = {}) => ({
  pk: 1,
  state: 'drafting',
  clock_armed: true,
  latest_round: 21,
  draft_options: { timer_enabled: true, grace_time_ms: 20000, reserve_time_ms: 30000, timeout_action: 'skip_turn' },
  draft_rounds: [{ pk: 21, pick_number: 1, captain: user(7), started_at: new Date(T0 - 5000).toISOString(), grace_time_ms: 20000 }],
  tournament: {
    teams: [
      { pk: 1, draft_order: 2, captain: user(8), draft_reserve_ms: 30000 },
      { pk: 2, draft_order: 1, captain: user(7), draft_reserve_ms: 30000 },
    ],
  },
  ...o,
});

describe('useTeamDraftTimerProps', () => {
  beforeEach(() => useDraftWebSocketStore.getState().reset());

  it('staff non-captain can control and resume; teams sorted by draft_order; active team from latest_round', () => {
    useDraftWebSocketStore.setState({ draftState: ds() as never, captainFresh: { 7: true } });
    const { result } = renderHook(() => useTeamDraftTimerProps(999, true));
    expect(result.current.clockBarProps).toMatchObject({ canControl: true, isMyTurn: false, activeTeamPk: 2, reserveTotalMs: 30000 });
    expect(result.current.clockBarProps.teams.map((t) => t.teamPk)).toEqual([2, 1]);
    expect(result.current.clockBarProps.teams[0].isConnected).toBe(true);
    expect(result.current.pauseOverlayProps.canResume).toBe(true);
  });

  it('spectator cannot control or resume', () => {
    useDraftWebSocketStore.setState({ draftState: ds() as never });
    const { result } = renderHook(() => useTeamDraftTimerProps(555, false));
    expect(result.current.clockBarProps.canControl).toBe(false);
    expect(result.current.pauseOverlayProps.canResume).toBe(false);
  });

  it('captain of the active round: isMyTurn', () => {
    useDraftWebSocketStore.setState({ draftState: ds() as never });
    expect(renderHook(() => useTeamDraftTimerProps(7, false)).result.current.clockBarProps.isMyTurn).toBe(true);
  });

  it('paused with no tick: overlay names the latest_round captain and the countdown is armed from serialized anchors', () => {
    useDraftWebSocketStore.setState({
      draftState: ds({ state: 'paused', clock_armed: false, paused_at: new Date(T0).toISOString() }) as never,
      tick: null,
      captainFresh: { 7: false },
    });
    const { result } = renderHook(() => useTeamDraftTimerProps(999, true));
    expect(result.current.pauseOverlayProps).toMatchObject({ draftStatus: 'paused', activeCaptain: user(7), isActiveCaptainDisconnected: true });
  });

  it('pending with tick null renders without a render loop and shows the lobby', () => {
    useDraftWebSocketStore.setState({ draftState: ds({ state: 'pending', clock_armed: false }) as never, tick: null });
    const { result } = renderHook(() => useTeamDraftTimerProps(7, false));
    expect(result.current.showLobby).toBe(true);
  });
});

describe('useTeamDraftTimerProps render cost', () => {
  beforeEach(() => {
    useDraftWebSocketStore.getState().reset();
    vi.useFakeTimers();
    vi.setSystemTime(T0);
  });
  afterEach(() => vi.useRealTimers());

  it('does not re-render the modal-level hook on animation frames while the clock is armed', () => {
    useDraftWebSocketStore.setState({ draftState: ds() as never });
    let renders = 0;
    const { result } = renderHook(() => {
      renders += 1;
      return useTeamDraftTimerProps(999, true);
    });
    const before = renders;
    for (let i = 0; i < 10; i += 1) {
      act(() => {
        vi.advanceTimersByTime(100);
      });
    }
    expect(renders).toBe(before);
    expect(result.current).not.toHaveProperty('countdown');
    expect(result.current.clockBarProps).not.toHaveProperty('countdown');
    expect(result.current.pauseOverlayProps).not.toHaveProperty('resumingRemainingMs');
  });
});
