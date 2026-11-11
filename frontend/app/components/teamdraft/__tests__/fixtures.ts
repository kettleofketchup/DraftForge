import type { UserType } from '~/index';
import type { DraftTick } from '../schemas';

export const T0 = Date.parse('2026-11-08T12:00:00.000Z');

export function user(pk: number): UserType {
  return { pk, username: `user${pk}`, nickname: `User ${pk}` } as UserType;
}

export const tick = (o: Partial<DraftTick> = {}): DraftTick => ({
  type: 'draft_tick',
  draft_state: 'drafting',
  server_time: new Date(T0).toISOString(),
  resuming_until: null,
  active_round_pk: 22,
  active_pick_number: 2,
  active_captain_id: 7,
  active_team_id: 1,
  round_started_at: new Date(T0 - 25_000).toISOString(),
  round_timed_out_at: null,
  round_grace_time_ms: 20_000,
  teams: [
    { team_id: 1, captain_id: 7, reserve_ms: 10_000, is_connected: true, is_ready: true },
    { team_id: 2, captain_id: 8, reserve_ms: 10_000, is_connected: false, is_ready: true },
  ],
  ...o,
});
