import { describe, expect, it } from 'vitest';
import type { LeadershipSettings } from '../schemas';
import {
  leadershipSettingsFieldErrors,
  leadershipSettingsPatch,
  pickLeadershipFormValues,
  slugifyTraitKey,
  traitFieldErrors,
  traitFormValues,
  traitPutItems,
} from '../settingsForm';

const VALUES = {
  review_window_hours: 48,
  rating_max_points: 10,
  rating_min_reviewers: 3,
  ranked_min_reviews: 5,
  prior_rating: 3,
  prior_strength: 4,
  half_life_days: 120,
  max_age_days: 365,
  leaderboard_public: true,
};

const SETTINGS: LeadershipSettings = {
  ...VALUES,
  defaults: VALUES,
  ranges: {},
  points: [
    {
      kind: 'captain',
      label: 'Captain',
      default: 5,
      points: 8,
      overridden: true,
    },
    { kind: 'coach', label: 'Coach', default: 2, points: 2, overridden: false },
  ],
};

const httpError = (data: unknown) => ({ response: { status: 400, data } });

describe('leadership settings form', () => {
  it('picks form values with points by kind', () => {
    expect(pickLeadershipFormValues(SETTINGS).points).toEqual({
      captain: 8,
      coach: 2,
    });
  });

  it('patches only changed fields and clears overrides set back to default', () => {
    const form = pickLeadershipFormValues(SETTINGS);
    const patch = leadershipSettingsPatch(
      {
        ...form,
        review_window_hours: 24,
        points: { captain: 5, coach: 3 },
      },
      SETTINGS,
    );
    expect(patch).toEqual({
      review_window_hours: 24,
      points: { captain: null, coach: 3 },
    });
  });

  it('is empty when nothing changed', () => {
    expect(
      leadershipSettingsPatch(pickLeadershipFormValues(SETTINGS), SETTINGS),
    ).toEqual({});
  });

  it('maps server field and point errors onto form paths', () => {
    expect(
      leadershipSettingsFieldErrors(
        httpError({
          review_window_hours: ['Too big.'],
          points: { captain: ['Too many.'] },
          detail: 'ignored',
        }),
      ),
    ).toEqual([
      ['review_window_hours', 'Too big.'],
      ['points.captain', 'Too many.'],
    ]);
  });
});

describe('trait editor helpers', () => {
  it('orders traits and writes contiguous orders back', () => {
    const form = traitFormValues([
      { key: 'b', label: 'B', order: 2, active: true },
      { key: 'a', label: 'A', order: 0, active: false },
    ]);
    expect(form.traits.map((t) => t.key)).toEqual(['a', 'b']);
    expect(traitPutItems(form)).toEqual([
      { key: 'a', label: 'A', order: 0, active: false },
      { key: 'b', label: 'B', order: 1, active: true },
    ]);
  });

  it('maps per-row server errors', () => {
    expect(
      traitFieldErrors(httpError({ traits: [{}, { label: ['Required.'] }] })),
    ).toEqual([['traits.1.label', 'Required.']]);
  });

  it('slugifies labels into unique keys', () => {
    expect(slugifyTraitKey('Shot Calling!', new Set(), 32)).toBe(
      'shot-calling',
    );
    expect(slugifyTraitKey('Calm', new Set(['calm']), 32)).toBe('calm-2');
    expect(slugifyTraitKey('***', new Set(), 32)).toBe('trait');
  });
});
