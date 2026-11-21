import { z } from 'zod';
import { MemberSummarySchema } from '~/features/contributions/schemas';

export const TRACK_KEYS = ['contribution', 'conduct', 'leadership'] as const;
export const TrackKeySchema = z.enum(TRACK_KEYS);
export type TrackKey = z.infer<typeof TrackKeySchema>;

export const MetricFormatSchema = z.enum(['int', 'percent', 'score5']);
export type MetricFormat = z.infer<typeof MetricFormatSchema>;

export const MetricSchema = z.object({
  key: z.string(),
  label: z.string(),
  format: MetricFormatSchema,
  periodic: z.boolean(),
  default: z.boolean(),
});
export type Metric = z.infer<typeof MetricSchema>;

export const TrackInfoSchema = z.object({
  key: TrackKeySchema,
  label: z.string(),
  metrics: z.array(MetricSchema).min(1),
  can_view_rows: z.boolean(),
  can_view_own: z.boolean(),
  board_open: z.boolean(),
  can_manage: z.boolean(),
});
export type TrackInfo = z.infer<typeof TrackInfoSchema>;

export const StandingRowSchema = z.object({
  member: MemberSummarySchema,
  value: z.number().nullable(),
  sample: z.number(),
  status: z.enum(['ranked', 'new']),
});
export type StandingRow = z.infer<typeof StandingRowSchema>;

export const StandingLeaderboardSchema = z.object({
  track: TrackKeySchema,
  metric: MetricSchema,
  period: z.string(),
  total: z.number().nullable(),
  rows: z.array(StandingRowSchema),
  rows_visible: z.boolean(),
  own_row: StandingRowSchema.nullable(),
});
export type StandingLeaderboard = z.infer<typeof StandingLeaderboardSchema>;

export function defaultMetric(track: TrackInfo): Metric {
  return track.metrics.find((m) => m.default) ?? track.metrics[0];
}
