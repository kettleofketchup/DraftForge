import { z } from 'zod';

export const ALL_TIME = 'all';

export const CONTRIBUTION_KINDS = [
  'promo_message',
  'event_host',
  'event_helper',
  'manual',
] as const;
export const ContributionKindSchema = z.enum(CONTRIBUTION_KINDS);
export type ContributionKind = z.infer<typeof ContributionKindSchema>;

export const KIND_LABELS: Record<ContributionKind, string> = {
  promo_message: 'Promotion message',
  event_host: 'Event host',
  event_helper: 'Event helper',
  manual: 'Manual award',
};

export const MemberSummarySchema = z.object({
  org_user_pk: z.number(),
  user_pk: z.number(),
  username: z.string(),
  nickname: z.string().nullable(),
  avatarUrl: z.string().nullable(),
});
export type MemberSummary = z.infer<typeof MemberSummarySchema>;

export const LeaderboardRowSchema = MemberSummarySchema.extend({
  points: z.number(),
  entries: z.number(),
});
export type LeaderboardRow = z.infer<typeof LeaderboardRowSchema>;

export const LeaderboardResponseSchema = z.object({
  period: z.string(),
  total: z.number(),
  rows_visible: z.boolean(),
  rows: z.array(LeaderboardRowSchema),
  own_row: LeaderboardRowSchema.nullable(),
});
export type LeaderboardResponse = z.infer<typeof LeaderboardResponseSchema>;

export const ContributionEntrySchema = z.object({
  pk: z.number(),
  kind: ContributionKindSchema,
  points: z.number(),
  event: z.object({ id: z.number(), name: z.string() }).nullable(),
  event_name: z.string(),
  occurred_at: z.string(),
  reason: z.string().optional(),
});
export type ContributionEntry = z.infer<typeof ContributionEntrySchema>;

export const MonthPointsSchema = z.object({
  month: z.string(),
  points: z.number(),
});
export type MonthPoints = z.infer<typeof MonthPointsSchema>;

export const MemberBreakdownSchema = z.object({
  member: MemberSummarySchema,
  totals: z.object({ all_time: z.number(), this_month: z.number() }),
  monthly: z.array(MonthPointsSchema),
  entries: z.array(ContributionEntrySchema),
});
export type MemberBreakdown = z.infer<typeof MemberBreakdownSchema>;

export const RATED_KINDS = [
  'promo_message',
  'event_host',
  'event_helper',
] as const;
export const RatedKindSchema = z.enum(RATED_KINDS);
export type RatedKind = z.infer<typeof RatedKindSchema>;

export const POINT_VALUE_MAX = 1000;
export const MANUAL_MIN_POINTS = 1;
export const MANUAL_MAX_POINTS = 1000;
export const REASON_MAX_LENGTH = 500;

export const PointValueRowSchema = z.object({
  kind: RatedKindSchema,
  points: z.number(),
  default: z.number(),
  is_default: z.boolean(),
});
export type PointValueRow = z.infer<typeof PointValueRowSchema>;

export const PointValueUpdateResultSchema = z.object({
  kind: RatedKindSchema,
  old: z.number(),
  new: z.number(),
  changed: z.number(),
});
export type PointValueUpdateResult = z.infer<
  typeof PointValueUpdateResultSchema
>;

export interface PointValueUpdate {
  /** null resets the kind to its default. */
  points: number | null;
  apply_to_past: boolean;
  since: string | null;
}

export const pointValueInputSchema = z
  .number({ message: 'Enter whole points' })
  .int({ message: 'Enter whole points' })
  .min(0, { message: 'At least 0 points' })
  .max(POINT_VALUE_MAX, { message: `At most ${POINT_VALUE_MAX} points` });

export const AdminEntrySchema = ContributionEntrySchema.extend({
  reason: z.string(),
  member: MemberSummarySchema,
  awarded_by: z.object({ pk: z.number(), username: z.string() }).nullable(),
});
export type AdminEntry = z.infer<typeof AdminEntrySchema>;

export const EntriesPageSchema = z.object({
  count: z.number(),
  limit: z.number(),
  offset: z.number(),
  results: z.array(AdminEntrySchema),
});
export type EntriesPage = z.infer<typeof EntriesPageSchema>;

export const ENTRIES_PAGE_SIZE = 50;

export interface EntriesFilters {
  period: string;
  kind: ContributionKind | null;
  offset: number;
}

function isCalendarDate(value: string): boolean {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return false;
  const [y, m, d] = [Number(match[1]), Number(match[2]), Number(match[3])];
  const date = new Date(Date.UTC(y, m - 1, d));
  return (
    date.getUTCFullYear() === y &&
    date.getUTCMonth() === m - 1 &&
    date.getUTCDate() === d
  );
}

export const calendarDateSchema = z
  .string()
  .refine(isCalendarDate, { message: 'Pick a valid date' });

export const manualAwardSchema = z.object({
  user_id: z.number().int().positive({ message: 'Pick a member' }),
  points: z
    .number({ message: 'Enter whole points' })
    .int({ message: 'Enter whole points' })
    .min(MANUAL_MIN_POINTS, { message: `At least ${MANUAL_MIN_POINTS} point` })
    .max(MANUAL_MAX_POINTS, { message: `At most ${MANUAL_MAX_POINTS} points` }),
  reason: z
    .string()
    .trim()
    .min(1, { message: 'Enter a reason' })
    .max(REASON_MAX_LENGTH, {
      message: `At most ${REASON_MAX_LENGTH} characters`,
    }),
  date: calendarDateSchema,
  event_id: z.number().int().positive().nullable().optional(),
});
export type ManualAwardInput = z.infer<typeof manualAwardSchema>;
