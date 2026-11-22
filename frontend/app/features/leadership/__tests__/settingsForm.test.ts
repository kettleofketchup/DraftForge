import { describe, expect, it } from 'vitest';
import type { LeadershipSettings } from '../schemas';
import {
  leadershipSettingsFieldErrors,
  leadershipSettingsPatch,
  pickLeadershipFormValues,
} from '../settingsForm';
import { leadershipSettings } from './fixtures';

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

describe('leadership settings form against the backend payload', () => {
  const saved = leadershipSettings({
    points: leadershipSettings().points.map((k) =>
      k.kind === 'captained' ? { ...k, points: 8, overridden: true } : k,
    ),
  });

  it('sends null for an override set back to its default', () => {
    const form = pickLeadershipFormValues(saved);
    expect(
      leadershipSettingsPatch(
        { ...form, points: { ...form.points, captained: 5 } },
        saved,
      ),
    ).toEqual({ points: { captained: null } });
  });

  it('sends a changed override as its value', () => {
    const form = pickLeadershipFormValues(saved);
    expect(
      leadershipSettingsPatch(
        { ...form, points: { ...form.points, placement_1: 12 } },
        saved,
      ),
    ).toEqual({ points: { placement_1: 12 } });
  });

  it('maps the max age detail onto max_age_days', () => {
    expect(
      leadershipSettingsFieldErrors(
        httpError({ detail: 'Max age must be at least the half-life.' }),
      ),
    ).toEqual([['max_age_days', 'Max age must be at least the half-life.']]);
  });
});
