import { z } from 'zod';
import { MemberSummarySchema } from '~/features/standing/members';

export const OUTCOMES = [
  'pending',
  'attended',
  'no_show',
  'late_cancel',
  'excused',
] as const;
export const OutcomeSchema = z.enum(OUTCOMES);
export type Outcome = z.infer<typeof OutcomeSchema>;

export const STAFF_SETTABLE_OUTCOMES = [
  'attended',
  'no_show',
  'late_cancel',
  'excused',
] as const satisfies readonly Outcome[];
export type StaffSettableOutcome = (typeof STAFF_SETTABLE_OUTCOMES)[number];

export const OUTCOME_LABELS: Record<Outcome, string> = {
  pending: 'Pending',
  attended: 'Attended',
  no_show: 'No-show',
  late_cancel: 'Late cancel',
  excused: 'Excused',
};

export const SOURCES = [
  'default',
  'staff',
  'ready_check',
  'cull',
  'voice',
  'late_cancel',
] as const;
export const SourceSchema = z.enum(SOURCES);
export type Source = z.infer<typeof SourceSchema>;

export const SOURCE_LABELS: Record<Source, string> = {
  default: 'Default',
  staff: 'Staff',
  ready_check: 'Ready check',
  cull: 'Cull',
  voice: 'Voice',
  late_cancel: 'Late cancel',
};

export const WALK_IN_LABEL = 'Walk-in';

export const VIRTUAL_OUTCOME_LABEL = 'Attended (default)';

export const REASON_MIN_LENGTH = 3;
export const REASON_MAX_LENGTH = 500;

export const TIERS = [
  'ok',
  'back_of_line',
  'require_approval',
  'block',
] as const;
export const TierSchema = z.enum(TIERS);
export type Tier = z.infer<typeof TierSchema>;

export const ScoreStatusSchema = z.enum(['new', 'scored']);
export type ScoreStatus = z.infer<typeof ScoreStatusSchema>;

export const ATTENDANCE_FLAGS = [
  'roll_call_unconfirmed',
  'dropped_unattributed',
] as const;
export const AttendanceFlagSchema = z.enum(ATTENDANCE_FLAGS);
export type AttendanceFlag = z.infer<typeof AttendanceFlagSchema>;

export const ATTENDANCE_FLAG_LABELS: Record<AttendanceFlag, string> = {
  roll_call_unconfirmed: 'Did not confirm at roll call',
  dropped_unattributed: 'Dropped, needs review',
};

const SetBySchema = z.object({ user_pk: z.number(), username: z.string() });
export type SetBy = z.infer<typeof SetBySchema>;

// backend/org/conduct/serializers.py HistoryItem
export const ConductHistoryItemSchema = z.object({
  event_id: z.number().nullable(),
  event_name: z.string(),
  event_starts_at: z.string(),
  outcome: OutcomeSchema,
  source: SourceSchema,
  committed: z.boolean(),
  finalized: z.boolean(),
  voided: z.boolean(),
  weight: z.number(),
  reason: z.string().optional(),
  set_by: SetBySchema.nullable().optional(),
});
export type ConductHistoryItem = z.infer<typeof ConductHistoryItemSchema>;

export const HISTORY_PAGE_SIZE = 50;

export interface HistoryPage {
  limit: number;
  offset: number;
}

// backend/org/conduct/views.py conduct_member
export const MemberConductSchema = z.object({
  member: MemberSummarySchema,
  show_rate: z.number(),
  status: ScoreStatusSchema,
  counted_events: z.number(),
  weighted_events: z.number(),
  totals: z.object({
    attended: z.number(),
    no_show: z.number(),
    late_cancel: z.number(),
    excused: z.number(),
  }),
  history: z.array(ConductHistoryItemSchema),
});
export type MemberConduct = z.infer<typeof MemberConductSchema>;

export const ConductSettingsValuesSchema = z.object({
  late_cancel_hours: z.number(),
  late_cancel_weight: z.number(),
  half_life_days: z.number(),
  max_age_days: z.number(),
  prior_show_rate: z.number(),
  prior_strength: z.number(),
  min_events: z.number(),
  leaderboard_public: z.boolean(),
  back_of_line_enabled: z.boolean(),
  back_of_line_below: z.number(),
  require_approval_enabled: z.boolean(),
  require_approval_below: z.number(),
  block_enabled: z.boolean(),
  block_below: z.number(),
  enforce_on_new_members: z.boolean(),
});
export type ConductSettingsValues = z.infer<typeof ConductSettingsValuesSchema>;
export type ConductSettingsField = keyof ConductSettingsValues;

// backend/org/conduct/serializers.py ConductSettingsData
export const ConductSettingsSchema = ConductSettingsValuesSchema.extend({
  defaults: ConductSettingsValuesSchema,
});
export type ConductSettings = z.infer<typeof ConductSettingsSchema>;

function wholeNumber(min: number, max: number) {
  return z
    .number({ message: 'Enter a whole number' })
    .int({ message: 'Enter a whole number' })
    .min(min, { message: `At least ${min}` })
    .max(max, { message: `At most ${max}` });
}

function hundredths(min: number, max: number) {
  return z
    .number({ message: 'Enter a number' })
    .min(min, { message: `At least ${min}` })
    .max(max, { message: `At most ${max}` })
    .refine((value) => Math.abs(value * 100 - Math.round(value * 100)) < 1e-9, {
      message: 'At most two decimal places',
    });
}

// Ranges mirror backend/org/conduct/constants.py SETTINGS_RANGES.
export const ConductSettingsFormSchema = z
  .object({
    late_cancel_hours: wholeNumber(0, 168),
    late_cancel_weight: hundredths(0, 1),
    half_life_days: wholeNumber(7, 730),
    max_age_days: wholeNumber(30, 1095),
    prior_show_rate: hundredths(0.05, 1),
    prior_strength: hundredths(0, 20),
    min_events: wholeNumber(1, 20),
    leaderboard_public: z.boolean(),
    back_of_line_enabled: z.boolean(),
    back_of_line_below: hundredths(0, 1),
    require_approval_enabled: z.boolean(),
    require_approval_below: hundredths(0, 1),
    block_enabled: z.boolean(),
    block_below: hundredths(0, 1),
    enforce_on_new_members: z.boolean(),
  })
  .refine((values) => values.max_age_days >= values.half_life_days, {
    message: 'Max age must be at least the half-life',
    path: ['max_age_days'],
  });
export type ConductSettingsForm = z.infer<typeof ConductSettingsFormSchema>;

// backend/org/conduct/attendance.py AttendanceRow; a signup without an OrgUser
// has a null org_user_pk.
export const AttendanceRowSchema = z.object({
  member: MemberSummarySchema.extend({ org_user_pk: z.number().nullable() }),
  org_user_pk: z.number().nullable(),
  signup_status: z.string().nullable(),
  outcome: OutcomeSchema,
  source: SourceSchema,
  committed: z.boolean(),
  virtual: z.boolean(),
  finalized: z.boolean(),
  voided: z.boolean(),
  flag: AttendanceFlagSchema.nullable(),
  set_by: SetBySchema.nullable(),
  reason: z.string(),
  show_rate: z.number(),
  status: ScoreStatusSchema,
});
export type AttendanceRow = z.infer<typeof AttendanceRowSchema>;

// backend/org/conduct/attendance.py AttendanceData
export const AttendanceSchema = z.object({
  event_id: z.number(),
  state: z.string(),
  finalized_at: z.string().nullable(),
  editable: z.boolean(),
  editable_reason: z.string().nullable(),
  rows: z.array(AttendanceRowSchema),
});
export type Attendance = z.infer<typeof AttendanceSchema>;

const StaffSettableOutcomeSchema = z.enum(STAFF_SETTABLE_OUTCOMES);

// backend/org/conduct/serializers.py AttendanceChangeSerializer
export const AttendanceChangeSchema = z.union([
  z
    .object({
      org_user_pk: z.number().int().positive(),
      outcome: StaffSettableOutcomeSchema,
    })
    .strict(),
  z
    .object({
      user_pk: z.number().int().positive(),
      outcome: StaffSettableOutcomeSchema,
    })
    .strict(),
]);
export type AttendanceChange = z.infer<typeof AttendanceChangeSchema>;

export const ReasonSchema = z
  .string()
  .trim()
  .min(REASON_MIN_LENGTH, {
    message: `At least ${REASON_MIN_LENGTH} characters`,
  })
  .max(REASON_MAX_LENGTH, {
    message: `At most ${REASON_MAX_LENGTH} characters`,
  });

// backend/org/conduct/serializers.py AttendancePutSerializer
export const AttendancePutSchema = z.object({
  changes: z
    .array(AttendanceChangeSchema)
    .min(1, { message: 'Pick at least one member' }),
  reason: ReasonSchema,
});
export type AttendancePut = z.infer<typeof AttendancePutSchema>;

// backend/org/conduct/serializers.py ForecastMember
export const ForecastMemberSchema = z.object({
  show_rate: z.number(),
  status: ScoreStatusSchema,
  tier: TierSchema,
  deferred: z.boolean(),
});
export type ForecastMember = z.infer<typeof ForecastMemberSchema>;

// backend/org/conduct/serializers.py ForecastData
export const ForecastSchema = z.object({
  seat_holders: z.number(),
  expected: z.number(),
  low: z.number(),
  high: z.number(),
  waitlisted: z.number(),
  pending_approval: z.number(),
  capacity: z.number().nullable(),
  expected_open_seats: z.number().nullable(),
  new_members: z.number(),
  members: z.record(z.string(), ForecastMemberSchema),
});
export type Forecast = z.infer<typeof ForecastSchema>;
