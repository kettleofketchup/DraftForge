import { describe, expect, it } from 'vitest';
import {
  EventCaptainReviewsSchema,
  EventReviewsSchema,
  LeadershipSettingsFormSchema,
  LeadershipSettingsSchema,
  MemberLeadershipSchema,
  ModerationReviewSchema,
  MyReviewSchema,
  PendingReviewSchema,
  ReleaseResultSchema,
  ReleaseStateSchema,
  ScoresFormSchema,
  TraitFormSchema,
  TraitsSchema,
  VoidReasonSchema,
} from '../schemas';
import {
  eventReviews,
  leadershipSettings,
  memberLeadership,
  moderationCaptain,
  moderationReview,
  myReview,
  pendingReview,
  SETTINGS_DEFAULTS,
  traits,
} from './fixtures';

const FORM_VALUES = {
  ...SETTINGS_DEFAULTS,
  points: { captained: 5, placement_1: 10 },
};

function formIssues(values: Record<string, unknown>) {
  const result = LeadershipSettingsFormSchema.safeParse(values);
  return result.success ? [] : result.error.issues;
}

function traitRows(count: number, active: number) {
  return Array.from({ length: count }, (_, i) => ({
    key: `trait_${i}`,
    label: `Trait ${i}`,
    active: i < active,
    saved: true,
  }));
}

describe('leadership response schemas', () => {
  it('parses every fixture', () => {
    expect(() =>
      MemberLeadershipSchema.parse(memberLeadership()),
    ).not.toThrow();
    expect(() => PendingReviewSchema.parse(pendingReview())).not.toThrow();
    expect(() => MyReviewSchema.parse(myReview())).not.toThrow();
    expect(() =>
      ModerationReviewSchema.parse(moderationReview()),
    ).not.toThrow();
    expect(() => EventReviewsSchema.parse(eventReviews())).not.toThrow();
    expect(() =>
      LeadershipSettingsSchema.parse(leadershipSettings()),
    ).not.toThrow();
    expect(() => TraitsSchema.parse(traits())).not.toThrow();
  });

  it('parses a member payload without events (others view)', () => {
    const { events: _events, ...rest } = memberLeadership();
    expect(MemberLeadershipSchema.parse(rest).events).toBeUndefined();
  });

  it('parses an unreleased event aggregate', () => {
    const parsed = MemberLeadershipSchema.parse(
      memberLeadership({
        rating: null,
        status: 'new',
        events: [
          {
            ...memberLeadership().events![0],
            released: false,
            reviews: null,
            rating: null,
            traits: null,
            captain_rating_points: null,
          },
        ],
      }),
    );
    expect(parsed.events![0].traits).toBeNull();
  });

  it('accepts a pending review with no scores yet', () => {
    const parsed = PendingReviewSchema.parse(
      pendingReview({ scores: null, void_kind: '' }),
    );
    expect(parsed.scores).toBeNull();
  });

  it('rejects an unknown void kind', () => {
    expect(() =>
      PendingReviewSchema.parse({ ...pendingReview(), void_kind: 'deleted' }),
    ).toThrow();
  });

  it("accepts the admin's own snapshot without reviews", () => {
    const own = {
      ...eventReviews().captains[0],
      own_snapshot: true,
      reviews: null,
    };
    expect(EventCaptainReviewsSchema.parse(own).reviews).toBeNull();
  });

  it('parses the release fields of a moderation payload', () => {
    const parsed = EventReviewsSchema.parse(
      eventReviews({
        require_staff_release: true,
        captains: [
          moderationCaptain({
            released: false,
            release_state: 'pending',
            auto_release_at: '2026-11-06T19:00:00Z',
            live_reviews: 4,
            release_floor: 3,
            can_release: true,
          }),
          moderationCaptain({
            org_user_id: 9,
            release_state: 'released',
            released_at: '2026-11-05T10:00:00Z',
            released_by: { pk: 3, username: 'mod' },
          }),
          moderationCaptain({
            org_user_id: 10,
            released: false,
            release_state: 'hidden',
            live_reviews: null,
            release_floor: null,
            own_snapshot: true,
            reviews: null,
          }),
        ],
      }),
    );
    expect(parsed.require_staff_release).toBe(true);
    expect(parsed.captains.map((c) => c.release_state)).toEqual([
      'pending',
      'released',
      'hidden',
    ]);
    expect(parsed.captains[0].auto_release_at).toBe('2026-11-06T19:00:00Z');
    expect(parsed.captains[1].released_by).toEqual({ pk: 3, username: 'mod' });
    expect(parsed.captains[2].live_reviews).toBeNull();
  });

  it('knows every release state and rejects others', () => {
    for (const state of [
      'voided',
      'open',
      'short',
      'pending',
      'released',
      'hidden',
    ]) {
      expect(ReleaseStateSchema.parse(state)).toBe(state);
    }
    expect(() => ReleaseStateSchema.parse('stamped')).toThrow();
  });

  it('rejects a moderation payload without the gate flag', () => {
    const { require_staff_release: _gate, ...rest } = eventReviews();
    expect(() => EventReviewsSchema.parse(rest)).toThrow();
  });

  it('parses a release result', () => {
    expect(
      ReleaseResultSchema.parse({
        released: [7],
        skipped: [{ org_user_id: 9, code: 'own_snapshot' }],
      }),
    ).toEqual({
      released: [7],
      skipped: [{ org_user_id: 9, code: 'own_snapshot' }],
    });
  });

  it('parses settings with release fields and moderator count', () => {
    const parsed = LeadershipSettingsSchema.parse(
      leadershipSettings({
        require_staff_release: true,
        auto_release_after_hours: 48,
        moderator_count: 2,
      }),
    );
    expect(parsed.auto_release_after_hours).toBe(48);
    expect(parsed.moderator_count).toBe(2);
    expect(
      LeadershipSettingsSchema.parse(leadershipSettings())
        .auto_release_after_hours,
    ).toBeNull();
  });

  it('accepts a moderated review without a rater', () => {
    const parsed = ModerationReviewSchema.parse(
      moderationReview({
        rater: null,
        voided_at: '2026-11-03T10:00:00Z',
        void_kind: 'moderated',
        void_reason: 'abusive',
      }),
    );
    expect(parsed.rater).toBeNull();
  });
});

describe('LeadershipSettingsFormSchema', () => {
  it('accepts the defaults', () => {
    expect(formIssues(FORM_VALUES)).toEqual([]);
  });

  it('rejects a minimum of one reviewer', () => {
    expect(
      formIssues({ ...FORM_VALUES, rating_min_reviewers: 1 })[0].path,
    ).toEqual(['rating_min_reviewers']);
  });

  it('rejects a review window above two weeks', () => {
    expect(
      formIssues({ ...FORM_VALUES, review_window_hours: 337 })[0].path,
    ).toEqual(['review_window_hours']);
  });

  it('rejects a max age below the half-life', () => {
    const issues = formIssues({
      ...FORM_VALUES,
      half_life_days: 180,
      max_age_days: 100,
    });
    expect(issues).toHaveLength(1);
    expect(issues[0].path).toEqual(['max_age_days']);
  });

  it('accepts no auto-release and the hour bounds', () => {
    for (const hours of [null, 1, 720]) {
      expect(
        formIssues({ ...FORM_VALUES, auto_release_after_hours: hours }),
      ).toEqual([]);
    }
  });

  it('rejects auto-release hours outside 1 to 720', () => {
    for (const hours of [0, 721, 1.5]) {
      expect(
        formIssues({ ...FORM_VALUES, auto_release_after_hours: hours })[0].path,
      ).toEqual(['auto_release_after_hours']);
    }
  });

  it('requires the gate flag to be a boolean', () => {
    expect(
      formIssues({ ...FORM_VALUES, require_staff_release: 'yes' })[0].path,
    ).toEqual(['require_staff_release']);
  });

  it('rejects a point override above 1000', () => {
    const issues = formIssues({ ...FORM_VALUES, points: { captained: 1001 } });
    expect(issues[0].path).toEqual(['points', 'captained']);
  });
});

describe('TraitFormSchema', () => {
  function issues(rows: unknown[]) {
    const result = TraitFormSchema.safeParse({ traits: rows });
    return result.success ? [] : result.error.issues;
  }

  it('rejects nine active traits', () => {
    expect(issues(traitRows(9, 9))[0].message).toBe(
      'At most 8 traits can be active',
    );
  });

  it('rejects no active trait', () => {
    expect(issues(traitRows(3, 0))[0].message).toBe(
      'Keep at least one trait active',
    );
  });

  it('rejects a duplicate key', () => {
    const rows = traitRows(2, 2);
    rows[1].key = rows[0].key;
    expect(issues(rows)).not.toEqual([]);
  });

  it('rejects a 49 character label', () => {
    const rows = traitRows(1, 1);
    rows[0].label = 'x'.repeat(49);
    expect(issues(rows)[0].path).toEqual(['traits', 0, 'label']);
  });

  it('rejects a key that is not a slug', () => {
    const rows = traitRows(1, 1);
    rows[0].key = 'Not a slug';
    expect(issues(rows)[0].path).toEqual(['traits', 0, 'key']);
  });

  it('accepts nine traits with eight active', () => {
    expect(issues(traitRows(9, 8))).toEqual([]);
  });
});

describe('ScoresFormSchema', () => {
  const schema = ScoresFormSchema(['a', 'b']);

  it('asks for a score on an unscored trait', () => {
    const result = schema.safeParse({ a: 3 });
    expect(result.success).toBe(false);
    expect(result.error!.issues).toHaveLength(1);
    expect(result.error!.issues[0].path).toEqual(['b']);
    expect(result.error!.issues[0].message).toBe('Pick a score');
  });

  it('rejects scores outside 1 to 5', () => {
    const result = schema.safeParse({ a: 0, b: 6 });
    expect(result.success).toBe(false);
    expect(result.error!.issues.map((i) => i.message)).toEqual([
      'Pick a score',
      'Pick a score',
    ]);
  });

  it('accepts 1 and 5', () => {
    expect(schema.safeParse({ a: 1, b: 5 }).success).toBe(true);
  });
});

describe('VoidReasonSchema', () => {
  it('rejects a blank reason', () => {
    expect(VoidReasonSchema.safeParse('   ').success).toBe(false);
  });

  it('accepts a short reason', () => {
    expect(VoidReasonSchema.parse(' x ')).toBe('x');
  });
});
