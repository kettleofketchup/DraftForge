process.env.TZ = 'Europe/Berlin';

import { describe, expect, it } from 'vitest';
import {
  DISCORD_CONFIG_DEFAULTS,
  DOTA_LOBBY_CONFIG_DEFAULTS,
  editEventFormSchema,
  utcToLocalInput,
} from '../schemas';

const START = '2026-11-15T01:00:00Z';
const END = '2026-11-15T03:00:00Z';
const TZ = 'America/New_York';

describe('edit form prefill in a Berlin browser', () => {
  it('runs under Europe/Berlin', () => {
    expect(new Date('2026-11-14T12:00:00Z').getTimezoneOffset()).toBe(-60);
  });

  it('prefills New York wall time, not browser time', () => {
    expect(utcToLocalInput(START, TZ)).toBe('2026-11-14T20:00');
    expect(utcToLocalInput(END, TZ)).toBe('2026-11-14T22:00');
  });

  it('accepts an unchanged 8-10 PM New York event', () => {
    const result = editEventFormSchema.safeParse({
      name: 'Inhouse',
      description: '',
      scheduled_at: utcToLocalInput(START, TZ),
      event_ends_at: utcToLocalInput(END, TZ),
      tournament_name: 'Cup',
      tournament_type: 'double_elimination',
      game_type: 1,
      draft_type: 'shuffle',
      game_mode: 'normal',
      custom_game_name: '',
      captains_draft_time: 10,
      lobby_steam_league_id: null,
      people_per_team: 5,
      number_of_teams: null,
      timezone: TZ,
      tournament_league: null,
      ...DISCORD_CONFIG_DEFAULTS,
      ...DOTA_LOBBY_CONFIG_DEFAULTS,
    });
    expect(result.error?.issues ?? []).toEqual([]);
    expect(result.success).toBe(true);
  });
});
