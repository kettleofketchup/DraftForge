import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  openSignupsFromForm,
  toRepeaterCreatePayload,
} from '~/components/events/createEventPayload';
import { localToUTC } from '~/components/events/schemas';
import { toPreviewValues } from '../toPreviewValues';

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-11-25T12:00:00Z'));
});
afterEach(() => vi.useRealTimers());

const base = {
  name: 'Friday Inhouse',
  description: '',
  timezone: 'America/New_York',
  discord_event_title: '',
  discord_post_signups: true,
  discord_post_signups_channel_id: '',
  discord_signup_role_ids: ['111'],
  dota_lobby_password: 'secret12',
  dota_lobby_password_mode: 'fixed',
  tournament_name: 'Night Cup',
  draft_timer_enabled: true,
};

describe('toPreviewValues', () => {
  it('converts the local start and end to UTC like the modals', () => {
    const out = toPreviewValues(
      {
        ...base,
        scheduled_at: '2026-12-04T18:00',
        event_ends_at: '2026-12-04T21:00',
      },
      'event',
    );
    expect(out.scheduled_at).toBe(
      localToUTC('2026-12-04T18:00', 'America/New_York'),
    );
    expect(out.scheduled_at).toBe('2026-12-04T23:00:00.000Z');
    expect(out.ends_at).toBe(
      localToUTC('2026-12-04T21:00', 'America/New_York'),
    );
    expect(out).not.toHaveProperty('event_ends_at');
  });

  it('sends only whitelisted keys, never the lobby password', () => {
    const out = toPreviewValues(base, 'event');
    expect(out).not.toHaveProperty('dota_lobby_password');
    expect(out).not.toHaveProperty('dota_lobby_password_mode');
    expect(out).not.toHaveProperty('tournament_name');
    expect(out).not.toHaveProperty('draft_timer_enabled');
    expect(out).toMatchObject({
      name: 'Friday Inhouse',
      discord_post_signups: true,
      discord_signup_role_ids: ['111'],
    });
  });

  it('drops half-edited blanks but keeps blank text that means something', () => {
    const out = toPreviewValues(
      { ...base, max_players: '', scheduled_at: '', timezone: null },
      'event',
    );
    expect(out).not.toHaveProperty('max_players');
    expect(out).not.toHaveProperty('scheduled_at');
    expect(out).not.toHaveProperty('timezone');
    expect(out.discord_event_title).toBe('');
    expect(out.discord_post_signups_channel_id).toBe('');
    expect(out.description).toBe('');
  });

  it('keeps a meaningful null', () => {
    expect(toPreviewValues({ ...base, min_mmr: null }, 'event').min_mmr).toBe(
      null,
    );
  });

  it('fills a blank series schedule the way Create does', () => {
    const form = {
      ...base,
      frequency: 'weekly',
      time_of_day: '',
      starts_at: '',
      generate_days_ahead: 7,
    };
    expect(toRepeaterCreatePayload(form)).toEqual({
      discord_notify_new_events: false,
      frequency: 'weekly',
      day_of_week: null,
      time_of_day: '19:00',
      starts_at: '2026-11-25',
      ends_at: null,
      generate_days_ahead: 7,
    });
    const out = toPreviewValues(form, 'repeater', { creating: true });
    expect(out).toMatchObject(toRepeaterCreatePayload(form));
    expect(out).not.toHaveProperty('scheduled_at');
  });

  it('does not invent a start date when editing a series', () => {
    const out = toPreviewValues(
      { ...base, frequency: 'weekly', time_of_day: '20:00', day_of_week: 5 },
      'repeater',
    );
    expect(out).not.toHaveProperty('starts_at');
    expect(out).toMatchObject({ time_of_day: '20:00', day_of_week: 5 });
  });

  it('derives open_signups from the signup open mode', () => {
    expect(openSignupsFromForm({ signup_open_mode: 'immediate' })).toBe(true);
    expect(openSignupsFromForm({ signup_open_mode: 'manual' })).toBe(false);
    expect(openSignupsFromForm({ signup_open_mode: 'scheduled' })).toBe(false);
  });
});
