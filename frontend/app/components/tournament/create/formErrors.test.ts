import { describe, expect, it } from 'vitest';
import {
  CreateTournamentSchema,
  LeagueMinimalSchema,
  SourceEventSchema,
  TournamentSchema,
} from '../schemas';
import { fieldErrorsFrom, tabForField } from './formErrors';

const minimalValid = {
  name: 'Cup',
  tournament_type: 'single_elimination',
  date_played: '2026-11-13T18:00',
  timezone: 'UTC',
};

describe('tabForField', () => {
  it('maps general fields', () => {
    expect(tabForField('league_id_write')).toBe('general');
    expect(tabForField('league')).toBe('general');
    expect(tabForField('name')).toBe('general');
  });

  it('maps lobby config fields to config', () => {
    expect(tabForField('captains_draft_time')).toBe('config');
    expect(tabForField('game_mode')).toBe('config');
    expect(tabForField('dota_lobby_region')).toBe('config');
    expect(tabForField('auto_create_hero_drafts')).toBe('config');
  });

  it('maps discord fields to discord', () => {
    expect(tabForField('discord_send_lobby_info')).toBe('discord');
    expect(tabForField('discord_send_draft_link')).toBe('discord');
  });

  it('falls back to general for unknown fields', () => {
    expect(tabForField('whatever')).toBe('general');
  });
});

describe('fieldErrorsFrom', () => {
  it('maps league_id_write onto league', () => {
    expect(fieldErrorsFrom({ league_id_write: ['x'] })).toEqual([
      { field: 'league', message: 'x' },
    ]);
  });

  it('accepts a plain string message', () => {
    expect(fieldErrorsFrom({ game_mode: 'y' })).toEqual([
      { field: 'game_mode', message: 'y' },
    ]);
  });

  it('drops keys that are not form fields', () => {
    expect(
      fieldErrorsFrom({
        detail: 'nope',
        error: 'e',
        non_field_errors: ['n'],
        draft_options: ['d'],
      }),
    ).toEqual([]);
  });

  it('returns nothing for non-object data', () => {
    expect(fieldErrorsFrom(undefined)).toEqual([]);
    expect(fieldErrorsFrom(null)).toEqual([]);
    expect(fieldErrorsFrom('Server error')).toEqual([]);
  });
});

describe('CreateTournamentSchema lobby config', () => {
  it('defaults game config fields', () => {
    const parsed = CreateTournamentSchema.parse(minimalValid);
    expect(parsed.game_type).toBe(1);
    expect(parsed.game_mode).toBe('normal');
    expect(parsed.lobby_steam_league_id).toBeNull();
    expect(parsed.captains_draft_time).toBe(10);
    expect(parsed.custom_game_name).toBe('');
  });

  it('rejects a draft time below one second in Captains Mode', () => {
    const result = CreateTournamentSchema.safeParse({
      ...minimalValid,
      game_mode: 'captains_mode',
      captains_draft_time: 0,
    });
    expect(result.success).toBe(false);
  });

  it('ignores the draft time outside Captains Mode', () => {
    const result = CreateTournamentSchema.safeParse({
      ...minimalValid,
      captains_draft_time: 0,
    });
    expect(result.success).toBe(true);
  });
});

describe('read schemas', () => {
  it('keep lobby config and league organization', () => {
    const t = TournamentSchema.parse({
      name: 'Cup',
      date_played: null,
      pk: 1,
      state: null,
      tournament_type: null,
      game_type: 1,
      game_mode: 'turbo',
      captains_draft_time: 20,
      custom_game_name: 'df',
    });
    expect(t.game_type).toBe(1);
    expect(t.captains_draft_time).toBe(20);
    expect(t.custom_game_name).toBe('df');

    const league = LeagueMinimalSchema.parse({
      pk: 9,
      name: 'L9',
      organization_name: null,
      organization: { pk: 8, name: 'Org' },
    });
    expect(league.organization?.pk).toBe(8);

    const ev = SourceEventSchema.parse({
      id: 1,
      name: 'E',
      event_repeater: null,
      organization_id: 8,
    });
    expect(ev.organization_id).toBe(8);
  });
});

describe('draft settings errors', () => {
  it('maps draft settings fields to config', () => {
    expect(tabForField('draft_grace_time_s')).toBe('config');
    expect(tabForField('hero_timer_enabled')).toBe('config');
  });

  it('flattens nested draft_options errors onto the seconds fields', () => {
    expect(
      fieldErrorsFrom({
        draft_options: {
          grace_time_ms: ['Too small'],
          hero_reserve_time_ms: ['Bad'],
          unknown: ['x'],
        },
      }),
    ).toEqual([
      { field: 'draft_grace_time_s', message: 'Too small' },
      { field: 'hero_reserve_time_s', message: 'Bad' },
    ]);
  });

  it('defaults draft settings when the form omits them', () => {
    const v = CreateTournamentSchema.parse(minimalValid);
    expect(v.draft_timer_enabled).toBe(true);
    expect(v.hero_reserve_time_s).toBe(90);
  });
});
