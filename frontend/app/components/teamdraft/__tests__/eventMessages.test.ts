import { describe, expect, it } from 'vitest';
import { getEventIcon, getEventMessage, getEventToast } from '~/components/teamdraft/eventMessages';
import type { DraftEvent, DraftEventType } from '~/types/draftEvent';

const ALL_TYPES: DraftEventType[] = ['draft_started','draft_completed','captain_assigned','player_picked','tie_roll','pick_undone','draft_lobby_opened','captain_ready','captain_unready','captain_connected','captain_disconnected','draft_started_by_staff','draft_force_started','round_started','draft_paused','draft_resumed','pick_timed_out','pick_skipped','pick_skip_unavailable','draft_options_changed'];
const ev = (event_type: DraftEventType, payload: object): DraftEvent => ({ pk: 1, event_type, payload: payload as DraftEvent['payload'], actor: null, created_at: '2026-11-08T12:00:00Z' });
const cap = { captain_id: 7, captain_name: 'Ana', captain_avatar_url: null, team_id: 1, team_name: 'T1' };
const skipped = { skipped_captain_id: 7, skipped_captain_name: 'Ana', skipped_team_id: 1, skipped_team_name: 'T1', next_captain_id: 8, next_captain_name: 'Bo', next_team_id: 2, next_team_name: 'T2', from_pick_number: 4, to_pick_number: 5, pick_duration_ms: 60000, reserve_used_ms: 30000 };

describe('getEventIcon / getEventMessage cover every DraftEventType', () => {
  it.each(ALL_TYPES)('%s has a specific icon', (t) => expect(getEventIcon(t)).not.toBe('📋'));
  it.each(ALL_TYPES)('%s has a specific message', (t) => {
    const payload = { ...cap, ...skipped, pick_number: 3, actor_name: 'Staff', not_ready: [], reason: 'manual', paused_by_name: 'Staff', elapsed_ms: 1, reserve_used_ms: 1, timer_enabled: true, grace_time_ms: 20000, reserve_time_ms: 10000, deferred_to_pick_number: 5, roll_rounds: [[{ team_id: 1, roll: 4 }]], winner_name: 'T1', picked_name: 'P', undone_player_name: 'P', is_active_captain: true };
    expect(getEventMessage(ev(t, payload))).not.toMatch(/Draft event occurred|Unknown event/);
  });
});

describe('pick_skipped copy', () => {
  it('names the deferred pick for snake/normal', () => {
    expect(getEventMessage(ev('pick_skipped', { ...skipped, deferred_to_pick_number: 5 }))).toBe('Ana ran out of time — Bo is up, Ana picks at #5');
  });
  it('omits the deferred pick for shuffle (null) and never renders #null', () => {
    const msg = getEventMessage(ev('pick_skipped', { ...skipped, deferred_to_pick_number: null }));
    expect(msg).toBe('Ana ran out of time — Bo is up');
    expect(msg).not.toContain('null');
  });
});

describe('draft_options_changed copy', () => {
  const opts = { grace_time_ms: 20000, reserve_time_ms: 10000, changed_by_id: 1, changed_by_name: 'Staff', from_state: 'drafting', to_state: 'drafting', pick_number: 3 };
  it('names the new clock when the timer turns on', () => {
    expect(getEventToast(ev('draft_options_changed', { ...opts, timer_enabled: true }))).toBe('Staff turned the pick clock on — 20s grace, 10s reserve');
  });
  it('says the clock is off when the timer turns off', () => {
    expect(getEventToast(ev('draft_options_changed', { ...opts, timer_enabled: false }))).toBe('Staff turned the pick clock off');
  });
  it('falls back to Staff when no actor is recorded', () => {
    expect(getEventMessage(ev('draft_options_changed', { ...opts, changed_by_name: null, timer_enabled: false }))).toBe('Staff turned the pick clock off');
  });
});

describe('getEventToast', () => {
  it('toasts captain_disconnected only for the active captain', () => {
    expect(getEventToast(ev('captain_disconnected', { ...cap, pick_number: 1, is_active_captain: true }))).toBe('Ana disconnected');
    expect(getEventToast(ev('captain_disconnected', { ...cap, pick_number: 1, is_active_captain: false }))).toBeNull();
  });
  it('is silent for feed-only events', () => {
    for (const t of ['pick_timed_out', 'round_started', 'captain_ready', 'captain_connected', 'draft_lobby_opened'] as DraftEventType[]) {
      expect(getEventToast(ev(t, { ...cap, pick_number: 1, elapsed_ms: 0, reserve_used_ms: 0, timer_enabled: true, grace_time_ms: 1, reserve_time_ms: 1, started_at: 'x', reserve_ms: 1 }))).toBeNull();
    }
  });
  it('distinguishes manual from disconnect pauses', () => {
    expect(getEventToast(ev('draft_paused', { ...cap, reason: 'manual', paused_by_id: 1, paused_by_name: 'Staff' }))).toBe('Draft paused by Staff');
    expect(getEventToast(ev('draft_paused', { ...cap, reason: 'captain_disconnected', paused_by_id: null, paused_by_name: null }))).toBe('Draft paused — Ana disconnected');
  });
});
