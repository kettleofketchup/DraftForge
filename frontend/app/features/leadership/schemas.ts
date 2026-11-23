import { z } from 'zod';
import { MemberSummarySchema } from '~/features/standing/members';

export const SCORE_VALUES = [1, 2, 3, 4, 5] as const;
export const MAX_ACTIVE_TRAITS = 8;
export const MIN_EVENT_AGGREGATE_REVIEWS = 3;
export const TRAIT_KEY_MAX_LENGTH = 32;
export const TRAIT_LABEL_MAX_LENGTH = 48;
export const VOID_REASON_MAX_LENGTH = 500;

export const VOID_KINDS = ['withdrawn', 'lifecycle', 'moderated'] as const;
export const VoidKindSchema = z.enum(['', ...VOID_KINDS]);
export type VoidKind = z.infer<typeof VoidKindSchema>;

const ScoresSchema = z.record(z.string(), z.number());
export type Scores = z.infer<typeof ScoresSchema>;

// backend/org/leadership/summary.py trait_data
export const TraitSchema = z.object({
  key: z.string(),
  label: z.string(),
  order: z.number(),
  active: z.boolean(),
});
export type Trait = z.infer<typeof TraitSchema>;

// backend/org/leadership/views.py leadership_traits
export const TraitsSchema = z.object({ traits: z.array(TraitSchema) });
export type Traits = z.infer<typeof TraitsSchema>;

// backend/org/leadership/summary.py rating_data
export const TraitRatingSchema = TraitSchema.extend({
  rating: z.number().nullable(),
});
export type TraitRating = z.infer<typeof TraitRatingSchema>;

// backend/org/leadership/queries.py EventAggregate
export const EventAggregateSchema = z.object({
  event_id: z.number(),
  event_name: z.string(),
  scheduled_at: z.string(),
  team_name: z.string(),
  placement: z.number().nullable(),
  released: z.boolean(),
  reviews: z.number().nullable(),
  rating: z.number().nullable(),
  traits: z
    .array(
      z.object({ key: z.string(), label: z.string(), average: z.number() }),
    )
    .nullable(),
  captain_rating_points: z.number().nullable(),
});
export type EventAggregate = z.infer<typeof EventAggregateSchema>;

export const RatingStatusSchema = z.enum(['ranked', 'new']);
export type RatingStatus = z.infer<typeof RatingStatusSchema>;

// backend/org/leadership/summary.py member_payload (period_points=True)
export const MemberLeadershipSchema = z.object({
  member: MemberSummarySchema,
  rating: z.number().nullable(),
  status: RatingStatusSchema,
  reviews: z.number(),
  traits: z.array(TraitRatingSchema),
  points: z.object({ all_time: z.number(), this_month: z.number() }),
  events: z.array(EventAggregateSchema).optional(),
});
export type MemberLeadership = z.infer<typeof MemberLeadershipSchema>;

// backend/org/leadership/views.py _snapshot_data
export const SnapshotSchema = z.object({
  event_id: z.number(),
  event_name: z.string(),
  captain_org_user_id: z.number(),
  captain: MemberSummarySchema,
  team_name: z.string(),
  window_closes_at: z.string(),
});
export type Snapshot = z.infer<typeof SnapshotSchema>;

// backend/org/leadership/views.py leadership_pending
export const PendingReviewSchema = SnapshotSchema.extend({
  traits: z.array(z.object({ key: z.string(), label: z.string() })),
  scores: ScoresSchema.nullable(),
  void_kind: VoidKindSchema,
});
export type PendingReview = z.infer<typeof PendingReviewSchema>;

// backend/org/leadership/views.py leadership_mine
export const MyReviewSchema = SnapshotSchema.extend({
  scores: ScoresSchema,
  submitted_at: z.string(),
  updated_at: z.string(),
  void_kind: VoidKindSchema,
});
export type MyReview = z.infer<typeof MyReviewSchema>;

// backend/org/leadership/views.py leadership_review (PUT)
export const ReviewResultSchema = z.object({
  scores: ScoresSchema,
  submitted_at: z.string(),
  updated_at: z.string(),
});
export type ReviewResult = z.infer<typeof ReviewResultSchema>;

// backend/org/leadership/views.py _review_data
export const ModerationReviewSchema = z.object({
  pk: z.number(),
  rater: MemberSummarySchema.nullable(),
  scores: ScoresSchema,
  submitted_at: z.string(),
  updated_at: z.string(),
  voided_at: z.string().nullable(),
  void_kind: VoidKindSchema,
  void_reason: z.string(),
});
export type ModerationReview = z.infer<typeof ModerationReviewSchema>;

// backend/org/leadership/constants.py ReleaseState, plus 'hidden' for the viewer's own snapshot
export const RELEASE_STATES = [
  'voided',
  'open',
  'short',
  'pending',
  'released',
  'hidden',
] as const;
export const ReleaseStateSchema = z.enum(RELEASE_STATES);
export type ReleaseState = z.infer<typeof ReleaseStateSchema>;

// backend/org/leadership/views.py _released_by
export const ReleasedBySchema = z.object({
  pk: z.number(),
  username: z.string(),
});
export type ReleasedBy = z.infer<typeof ReleasedBySchema>;

// backend/org/leadership/views.py leadership_event_reviews (captains[])
export const EventCaptainReviewsSchema = z.object({
  org_user_id: z.number(),
  captain: MemberSummarySchema,
  team_name: z.string(),
  window_closes_at: z.string(),
  voided_at: z.string().nullable(),
  released: z.boolean(),
  release_state: ReleaseStateSchema,
  released_at: z.string().nullable(),
  released_by: ReleasedBySchema.nullable(),
  auto_release_at: z.string().nullable(),
  live_reviews: z.number().int().nullable(),
  release_floor: z.number().int().nullable(),
  can_release: z.boolean(),
  own_snapshot: z.boolean(),
  reviews: z.array(ModerationReviewSchema).nullable(),
  aggregate: EventAggregateSchema.nullable(),
});
export type EventCaptainReviews = z.infer<typeof EventCaptainReviewsSchema>;

// backend/org/leadership/views.py leadership_event_reviews
export const EventReviewsSchema = z.object({
  event: z.object({ pk: z.number(), name: z.string() }),
  require_staff_release: z.boolean(),
  captains: z.array(EventCaptainReviewsSchema),
});
export type EventReviews = z.infer<typeof EventReviewsSchema>;

// backend/org/leadership/views.py leadership_event_release
export const ReleaseResultSchema = z.object({
  released: z.array(z.number()),
  skipped: z.array(z.object({ org_user_id: z.number(), code: z.string() })),
});
export type ReleaseResult = z.infer<typeof ReleaseResultSchema>;

// backend/org/leadership/constants.py SETTINGS_DEFAULTS
export const LEADERSHIP_SETTINGS_FIELDS = [
  'review_window_hours',
  'rating_max_points',
  'rating_min_reviewers',
  'ranked_min_reviews',
  'prior_rating',
  'prior_strength',
  'half_life_days',
  'max_age_days',
  'leaderboard_public',
  'require_staff_release',
  'auto_release_after_hours',
] as const;

export const LeadershipSettingsValuesSchema = z.object({
  review_window_hours: z.number(),
  rating_max_points: z.number(),
  rating_min_reviewers: z.number(),
  ranked_min_reviews: z.number(),
  prior_rating: z.number(),
  prior_strength: z.number(),
  half_life_days: z.number(),
  max_age_days: z.number(),
  leaderboard_public: z.boolean(),
  require_staff_release: z.boolean(),
  auto_release_after_hours: z.number().int().nullable(),
});
export type LeadershipSettingsValues = z.infer<
  typeof LeadershipSettingsValuesSchema
>;
export type LeadershipSettingsField = keyof LeadershipSettingsValues;

// backend/org/leadership/settings.py kind_points
export const KindPointsSchema = z.object({
  kind: z.string(),
  label: z.string(),
  default: z.number(),
  points: z.number(),
  overridden: z.boolean(),
});
export type KindPoints = z.infer<typeof KindPointsSchema>;

// backend/org/leadership/serializers.py settings_data
export const LeadershipSettingsSchema = LeadershipSettingsValuesSchema.extend({
  defaults: LeadershipSettingsValuesSchema,
  ranges: z.record(z.string(), z.tuple([z.number(), z.number()])),
  points: z.array(KindPointsSchema),
  moderator_count: z.number().int(),
});
export type LeadershipSettings = z.infer<typeof LeadershipSettingsSchema>;

function wholeNumber(min: number, max: number) {
  return z
    .number({ message: 'Enter a whole number' })
    .int({ message: 'Enter a whole number' })
    .min(min, { message: `At least ${min}` })
    .max(max, { message: `At most ${max}` });
}

function decimal(min: number, max: number) {
  return z
    .number({ message: 'Enter a number' })
    .min(min, { message: `At least ${min}` })
    .max(max, { message: `At most ${max}` });
}

// Ranges mirror backend/org/leadership/constants.py SETTINGS_RANGES and
// serializers.py POINT_VALUE_MAX.
export const LeadershipSettingsFormSchema = z
  .object({
    review_window_hours: wholeNumber(1, 336),
    rating_max_points: wholeNumber(0, 100),
    rating_min_reviewers: wholeNumber(2, 20),
    ranked_min_reviews: wholeNumber(1, 50),
    prior_rating: decimal(1, 5),
    prior_strength: decimal(0, 20),
    half_life_days: wholeNumber(7, 730),
    max_age_days: wholeNumber(30, 1825),
    leaderboard_public: z.boolean(),
    require_staff_release: z.boolean(),
    auto_release_after_hours: wholeNumber(1, 720).nullable(),
    points: z.record(z.string(), wholeNumber(0, 1000)),
  })
  .refine((values) => values.max_age_days >= values.half_life_days, {
    message: 'Max age must be at least the half-life',
    path: ['max_age_days'],
  });
export type LeadershipSettingsForm = z.infer<
  typeof LeadershipSettingsFormSchema
>;

export type LeadershipSettingsPatch = Partial<LeadershipSettingsValues> & {
  points?: Record<string, number | null>;
};

// backend/org/leadership/serializers.py TraitItemSerializer
export const TraitFormSchema = z
  .object({
    traits: z.array(
      z.object({
        key: z
          .string()
          .min(1, { message: 'Enter a key' })
          .max(TRAIT_KEY_MAX_LENGTH, {
            message: `At most ${TRAIT_KEY_MAX_LENGTH} characters`,
          })
          .regex(/^[-a-zA-Z0-9_]+$/, {
            message: 'Use letters, numbers, dashes and underscores',
          }),
        label: z
          .string()
          .trim()
          .min(1, { message: 'Enter a name' })
          .max(TRAIT_LABEL_MAX_LENGTH, {
            message: `At most ${TRAIT_LABEL_MAX_LENGTH} characters`,
          }),
        active: z.boolean(),
        saved: z.boolean(),
      }),
    ),
  })
  .superRefine(({ traits }, ctx) => {
    const active = traits.filter((t) => t.active).length;
    if (active < 1) {
      ctx.addIssue({
        code: 'custom',
        path: ['traits'],
        message: 'Keep at least one trait active',
      });
    }
    if (active > MAX_ACTIVE_TRAITS) {
      ctx.addIssue({
        code: 'custom',
        path: ['traits'],
        message: `At most ${MAX_ACTIVE_TRAITS} traits can be active`,
      });
    }
    const seen = new Set<string>();
    traits.forEach((t, index) => {
      if (seen.has(t.key)) {
        ctx.addIssue({
          code: 'custom',
          path: ['traits', index, 'key'],
          message: 'Each trait needs its own key',
        });
      }
      seen.add(t.key);
    });
  });
export type TraitForm = z.infer<typeof TraitFormSchema>;

// backend/org/leadership/serializers.py ReviewPutSerializer
export function ScoresFormSchema(keys: readonly string[]) {
  const score = z
    .number({ error: 'Pick a score' })
    .int({ error: 'Pick a score' })
    .min(1, { error: 'Pick a score' })
    .max(5, { error: 'Pick a score' });
  return z.object(Object.fromEntries(keys.map((key) => [key, score])));
}

// backend/org/leadership/serializers.py ReasonSerializer
export const VoidReasonSchema = z
  .string()
  .trim()
  .min(1, { message: 'Give a reason' })
  .max(VOID_REASON_MAX_LENGTH, {
    message: `At most ${VOID_REASON_MAX_LENGTH} characters`,
  });
