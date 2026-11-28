import type { OrgFeatureAccess } from '~/features/org-features';
import { makeOrgFeatureAccess } from '~/features/org-features/__tests__/makeOrgFeatureAccess';
import type { TrackInfo } from '~/features/standing/schemas';
import type {
  EventAggregate,
  EventCaptainReviews,
  EventReviews,
  LeadershipSettings,
  LeadershipSettingsValues,
  MemberLeadership,
  ModerationReview,
  MyReview,
  PendingReview,
  Traits,
} from '../schemas';

export const CAPTAIN = {
  org_user_pk: 7,
  user_pk: 11,
  username: 'alice',
  nickname: null,
  discordNickname: null,
  guildNickname: null,
  avatarUrl: null,
};

export const RATER = {
  org_user_pk: 8,
  user_pk: 12,
  username: 'bob',
  nickname: null,
  discordNickname: null,
  guildNickname: null,
  avatarUrl: null,
};

export const DEFAULT_TRAITS = [
  { key: 'communication', label: 'Communication' },
  { key: 'drafting', label: 'Drafting' },
  { key: 'composure', label: 'Composure' },
  { key: 'sportsmanship', label: 'Sportsmanship' },
];

const SCORES = {
  communication: 4,
  drafting: 3,
  composure: 5,
  sportsmanship: 4,
};

export function traits(overrides: Partial<Traits> = {}): Traits {
  return {
    traits: DEFAULT_TRAITS.map((t, order) => ({ ...t, order, active: true })),
    ...overrides,
  };
}

export function eventAggregate(
  overrides: Partial<EventAggregate> = {},
): EventAggregate {
  return {
    event_id: 5,
    event_name: 'Inhouse night',
    scheduled_at: '2026-11-01T19:00:00Z',
    team_name: 'Team alice',
    placement: 1,
    released: true,
    reviews: 3,
    rating: 4.1,
    traits: DEFAULT_TRAITS.map((t) => ({ ...t, average: 4 })),
    captain_rating_points: 8,
    ...overrides,
  };
}

export function memberLeadership(
  overrides: Partial<MemberLeadership> = {},
): MemberLeadership {
  return {
    member: CAPTAIN,
    rating: 4.1,
    status: 'ranked',
    reviews: 6,
    traits: DEFAULT_TRAITS.map((t, order) => ({
      ...t,
      order,
      active: true,
      rating: 4,
    })),
    points: { all_time: 42, this_month: 13 },
    events: [eventAggregate()],
    feedback_private: false,
    ...overrides,
  };
}

const SNAPSHOT = {
  event_id: 5,
  event_name: 'Inhouse night',
  captain_org_user_id: 7,
  captain: CAPTAIN,
  team_name: 'Team alice',
  window_closes_at: '2026-11-04T19:00:00Z',
};

export function pendingReview(
  overrides: Partial<PendingReview> = {},
): PendingReview {
  return {
    ...SNAPSHOT,
    traits: DEFAULT_TRAITS,
    scores: null,
    void_kind: '',
    ...overrides,
  };
}

export function myReview(overrides: Partial<MyReview> = {}): MyReview {
  return {
    ...SNAPSHOT,
    scores: SCORES,
    submitted_at: '2026-11-02T10:00:00Z',
    updated_at: '2026-11-02T10:00:00Z',
    void_kind: '',
    ...overrides,
  };
}

export function moderationReview(
  overrides: Partial<ModerationReview> = {},
): ModerationReview {
  return {
    pk: 31,
    rater: RATER,
    scores: SCORES,
    submitted_at: '2026-11-02T10:00:00Z',
    updated_at: '2026-11-02T10:00:00Z',
    voided_at: null,
    void_kind: '',
    void_reason: '',
    ...overrides,
  };
}

export function moderationCaptain(
  overrides: Partial<EventCaptainReviews> = {},
): EventCaptainReviews {
  return {
    org_user_id: 7,
    captain: CAPTAIN,
    team_name: 'Team alice',
    window_closes_at: '2026-11-04T19:00:00Z',
    voided_at: null,
    released: true,
    release_state: 'released',
    released_at: null,
    released_by: null,
    auto_release_at: null,
    live_reviews: 3,
    release_floor: 3,
    can_release: false,
    own_snapshot: false,
    reviews: [moderationReview()],
    aggregate: null,
    feedback_private: false,
    ...overrides,
  };
}

export function eventReviews(
  overrides: Partial<EventReviews> = {},
): EventReviews {
  return {
    event: { pk: 5, name: 'Inhouse night' },
    require_staff_release: false,
    captains: [moderationCaptain()],
    ...overrides,
  };
}

export const SETTINGS_DEFAULTS: LeadershipSettingsValues = {
  review_window_hours: 72,
  review_dms_enabled: false,
  rating_max_points: 10,
  rating_min_reviewers: 2,
  ranked_min_reviews: 3,
  prior_rating: 3.0,
  prior_strength: 2.0,
  half_life_days: 180,
  max_age_days: 730,
  leaderboard_public: false,
  require_staff_release: false,
  auto_release_after_hours: null,
  captain_feedback_visible: true,
};

export function leadershipSettings(
  overrides: Partial<LeadershipSettings> = {},
): LeadershipSettings {
  return {
    ...SETTINGS_DEFAULTS,
    defaults: SETTINGS_DEFAULTS,
    ranges: {
      review_window_hours: [1, 336],
      rating_max_points: [0, 100],
      rating_min_reviewers: [2, 20],
      ranked_min_reviews: [1, 50],
      prior_rating: [1, 5],
      prior_strength: [0, 20],
      half_life_days: [7, 730],
      max_age_days: [30, 1825],
      auto_release_after_hours: [1, 720],
    },
    points: [
      { kind: 'captained', label: 'Captained a team', default: 5 },
      { kind: 'placement_1', label: 'Team placed 1st', default: 10 },
      { kind: 'placement_2', label: 'Team placed 2nd', default: 6 },
      { kind: 'placement_3', label: 'Team placed 3rd', default: 3 },
      { kind: 'draft_completed', label: 'Draft completed', default: 2 },
    ].map((k) => ({ ...k, points: k.default, overridden: false })),
    moderator_count: 1,
    ...overrides,
  };
}

export function leadershipTrackInfo(
  overrides: Partial<TrackInfo> = {},
): TrackInfo {
  return {
    key: 'leadership',
    label: 'Leadership',
    metrics: [
      {
        key: 'rating',
        label: 'Rating',
        format: 'score5',
        periodic: false,
        default: true,
      },
    ],
    can_view_rows: true,
    can_view_own: true,
    board_open: true,
    can_manage: false,
    can_moderate: false,
    own_private: false,
    ...overrides,
  };
}

/** Access for a viewer whose org lists the leadership track; `track: null` leaves it locked. */
export function leadershipFeatureAccess({
  viewerPk = 12,
  track = {},
}: {
  viewerPk?: number;
  track?: Partial<TrackInfo> | null;
} = {}): OrgFeatureAccess {
  return makeOrgFeatureAccess({
    viewerPk,
    standingTracks: track === null ? [] : [leadershipTrackInfo(track)],
  });
}
