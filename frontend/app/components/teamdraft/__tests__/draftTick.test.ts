import { expect, it } from 'vitest';
import { DraftTickSchema } from '~/components/teamdraft/schemas';

const frame = (reserve_ms: number | null) => ({
  type: 'draft_tick',
  draft_state: 'drafting',
  server_time: '2026-11-08T12:00:00Z',
  resuming_until: null,
  active_round_pk: 1,
  active_pick_number: 1,
  active_captain_id: 7,
  active_team_id: 1,
  round_started_at: '2026-11-08T11:59:30Z',
  round_timed_out_at: null,
  round_grace_time_ms: 30000,
  teams: [{ team_id: 1, captain_id: 7, reserve_ms, is_connected: true, is_ready: true }],
});

it('accepts a tick whose team reserve_ms is null (unseeded pool)', () => {
  expect(DraftTickSchema.safeParse(frame(null)).success).toBe(true);
  expect(DraftTickSchema.safeParse(frame(1000)).success).toBe(true);
});
