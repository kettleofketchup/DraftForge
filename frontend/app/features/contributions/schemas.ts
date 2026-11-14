import { z } from 'zod';

export const ALL_TIME = 'all';

export const CONTRIBUTION_KINDS = ['promo_message', 'event_host', 'event_helper', 'manual'] as const;
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
