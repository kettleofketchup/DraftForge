// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('~/components/player', () => ({
  PlayerPopover: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}));
vi.mock('~/components/user/UserAvatar', () => ({ UserAvatar: () => null }));

import { DraftTopBar } from '~/components/herodraft/DraftTopBar';
import {
  HeroDraftSchema,
  HeroDraftTickSchema,
} from '~/components/herodraft/schemas';
import type { HeroDraft, HeroDraftTick } from '~/components/herodraft/types';
import { isTimerEnabled } from '~/components/herodraft/useDraftCountdown';
import { useHeroDraftStore } from '~/store/heroDraftStore';

const captain = { pk: 1, username: 'c', nickname: null, avatar: null };
const team = (id: number, isFirst: boolean) => ({
  id,
  tournament_team: 30 + id,
  captain: { ...captain, pk: id },
  team_name: `Team ${id}`,
  members: [],
  is_first_pick: isFirst,
  is_radiant: null,
  reserve_time_remaining: 5_000,
  is_ready: true,
  is_connected: true,
});
const rawDraft = {
  id: 2,
  game: 99,
  tournament_id: 8,
  state: 'drafting' as const,
  roll_winner: null,
  draft_teams: [team(1, true), team(2, false)],
  rounds: [
    {
      id: 1,
      round_number: 1,
      action_type: 'ban' as const,
      hero_id: null,
      state: 'active' as const,
      grace_time_ms: 30_000,
      started_at: '2026-11-08T11:59:00Z',
      completed_at: null,
      draft_team: 1,
      team_name: 'Team 1',
    },
  ],
  current_round: 0,
  created_at: '2026-11-08T00:00:00Z',
  updated_at: '2026-11-08T00:00:00Z',
};
const tick: HeroDraftTick = {
  type: 'herodraft_tick',
  draft_state: 'drafting',
  server_time: '2026-11-08T12:00:00Z',
  current_round: 0,
  active_team_id: 1,
  round_started_at: '2026-11-08T11:59:00Z',
  round_grace_time_ms: 30_000,
  team_a_id: 1,
  team_a_reserve_ms: 5_000,
  team_b_id: 2,
  team_b_reserve_ms: 5_000,
  resuming_until: null,
};

afterEach(() => {
  useHeroDraftStore.setState({ draft: null, tick: null });
});

describe('timer_enabled schema', () => {
  it('defaults to true when absent (older payloads)', () => {
    expect(HeroDraftSchema.parse(rawDraft).timer_enabled).toBe(true);
  });

  it('keeps an explicit false', () => {
    expect(
      HeroDraftSchema.parse({ ...rawDraft, timer_enabled: false })
        .timer_enabled,
    ).toBe(false);
  });

  it('accepts an optional timer_enabled on ticks', () => {
    expect(HeroDraftTickSchema.parse(tick).timer_enabled).toBeUndefined();
    expect(
      HeroDraftTickSchema.parse({ ...tick, timer_enabled: false })
        .timer_enabled,
    ).toBe(false);
  });
});

describe('isTimerEnabled', () => {
  it('is true unless the draft or tick says false', () => {
    expect(isTimerEnabled(null, null)).toBe(true);
    expect(isTimerEnabled({ timer_enabled: true }, {})).toBe(true);
    expect(isTimerEnabled({ timer_enabled: false }, null)).toBe(false);
    expect(
      isTimerEnabled({ timer_enabled: true }, { timer_enabled: false }),
    ).toBe(false);
  });
});

describe('DraftTopBar timer rendering', () => {
  const renderBar = (draft: HeroDraft) => {
    useHeroDraftStore.setState({ draft, tick });
    return render(<DraftTopBar draft={draft} tick={tick} />);
  };

  it('shows grace and reserve countdowns when the timer is on', () => {
    renderBar(HeroDraftSchema.parse(rawDraft));
    expect(screen.getByTestId('herodraft-grace-time')).toBeTruthy();
    expect(screen.getByTestId('herodraft-team-a-reserve-time')).toBeTruthy();
    expect(screen.queryByTestId('herodraft-no-timer')).toBeNull();
  });

  it('hides countdowns and urgency styling when the timer is off', () => {
    const { container } = renderBar(
      HeroDraftSchema.parse({ ...rawDraft, timer_enabled: false }),
    );
    expect(screen.getByTestId('herodraft-no-timer').textContent).toBe(
      'No turn timer',
    );
    expect(screen.queryByTestId('herodraft-grace-time')).toBeNull();
    expect(screen.queryByTestId('herodraft-team-a-reserve-time')).toBeNull();
    expect(screen.queryByTestId('herodraft-team-b-reserve-time')).toBeNull();
    expect(
      container.querySelector(
        '.animate-reserve-critical, .animate-grace-urgent',
      ),
    ).toBeNull();
    expect(screen.getByTestId('herodraft-current-action').textContent).toBe(
      'ban',
    );
  });

  it('hides countdowns when only the tick reports the timer off', () => {
    const draft = HeroDraftSchema.parse(rawDraft);
    const offTick = { ...tick, timer_enabled: false };
    useHeroDraftStore.setState({ draft, tick: offTick });
    render(<DraftTopBar draft={draft} tick={offTick} />);
    expect(screen.getByTestId('herodraft-no-timer')).toBeTruthy();
    expect(screen.queryByTestId('herodraft-grace-time')).toBeNull();
  });
});
