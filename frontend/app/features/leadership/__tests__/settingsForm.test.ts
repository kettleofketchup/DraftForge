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
  require_staff_release: false,
  auto_release_after_hours: null,
};

const SETTINGS: LeadershipSettings = {
  ...VALUES,
  defaults: VALUES,
  ranges: {},
  moderator_count: 1,
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

describe('leadership settings form release fields', () => {
  it('round-trips no auto-release as null', () => {
    const saved = leadershipSettings();
    const form = pickLeadershipFormValues(saved);
    expect(form.auto_release_after_hours).toBeNull();
    expect(form.require_staff_release).toBe(false);
    expect(leadershipSettingsPatch(form, saved)).toEqual({});
  });

  it('round-trips a fallback of 48 hours', () => {
    const saved = leadershipSettings({
      require_staff_release: true,
      auto_release_after_hours: 48,
    });
    const form = pickLeadershipFormValues(saved);
    expect(form.auto_release_after_hours).toBe(48);
    expect(form.require_staff_release).toBe(true);
    expect(leadershipSettingsPatch(form, saved)).toEqual({});
  });

  it('sends only the changed gate and hours', () => {
    const saved = leadershipSettings();
    const form = pickLeadershipFormValues(saved);
    expect(
      leadershipSettingsPatch(
        { ...form, require_staff_release: true, auto_release_after_hours: 48 },
        saved,
      ),
    ).toEqual({ require_staff_release: true, auto_release_after_hours: 48 });
  });

  it('sends null when the fallback is cleared', () => {
    const saved = leadershipSettings({
      require_staff_release: true,
      auto_release_after_hours: 48,
    });
    const form = pickLeadershipFormValues(saved);
    expect(
      leadershipSettingsPatch(
        { ...form, auto_release_after_hours: null },
        saved,
      ),
    ).toEqual({ auto_release_after_hours: null });
  });

  it('maps a server error on the hours field', () => {
    expect(
      leadershipSettingsFieldErrors(
        httpError({
          auto_release_after_hours: [
            'Ensure this value is less than or equal to 720.',
          ],
        }),
      ),
    ).toEqual([
      [
        'auto_release_after_hours',
        'Ensure this value is less than or equal to 720.',
      ],
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

  it('leaves a non-field detail to the caller', () => {
    expect(
      leadershipSettingsFieldErrors(
        httpError({ detail: 'Max age must be at least the half-life.' }),
      ),
    ).toEqual([]);
  });
});
