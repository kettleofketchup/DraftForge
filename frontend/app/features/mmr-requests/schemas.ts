import { z } from 'zod';
import {
  DEFAULT_MMR_BOUNDS,
  GAME_MMR_BOUNDS,
  type GameTypeValue,
} from '~/components/game/constants';

export * from './summary.generated';

export const MAX_SCREENSHOT_BYTES = 8 * 1024 * 1024;
export const SCREENSHOT_TYPES = [
  'image/png',
  'image/jpeg',
  'image/webp',
] as const;
export const TEXT_MAX_LENGTH = 500;

export const MMR_REQUEST_STATUSES = [
  'pending',
  'approved',
  'rejected',
  'cancelled',
  'superseded',
] as const;
export const MmrRequestStatusSchema = z.enum(MMR_REQUEST_STATUSES);
export type MmrRequestStatus = z.infer<typeof MmrRequestStatusSchema>;
export type MmrQueueStatus = MmrRequestStatus | 'all';

export const MmrTargetSchema = z.enum(['org', 'league']);
export type MmrTarget = z.infer<typeof MmrTargetSchema>;

export const MmrChangeRequestSchema = z.object({
  id: z.number().int(),
  target: MmrTargetSchema,
  game_type: z.number().int(),
  status: MmrRequestStatusSchema,
  source: z.enum(['member', 'staff']),
  requested_mmr: z.number().int(),
  approved_mmr: z.number().int().nullable(),
  previous_mmr: z.number().int(),
  previous_verified: z.boolean(),
  note: z.string(),
  rejection_reason: z.string(),
  reviewed_at: z.string().nullable(),
  reviewed_by_username: z.string().nullable(),
  created_at: z.string(),
  subject: z.object({
    pk: z.number().int(),
    username: z.string(),
    nickname: z.string().nullable(),
    avatarUrl: z.string().nullable(),
  }),
  requester_username: z.string(),
  organization: z.object({ pk: z.number().int(), name: z.string() }),
  league: z.object({ pk: z.number().int(), name: z.string() }).nullable(),
  current_mmr: z.number().int(),
  current_verified: z.boolean(),
  has_screenshot: z.boolean(),
  screenshot_url: z.string().nullable(),
  screenshot_purged_at: z.string().nullable(),
  can_review: z.boolean(),
});
export type MmrChangeRequest = z.infer<typeof MmrChangeRequestSchema>;

export const MmrRequestListSchema = z.array(MmrChangeRequestSchema);

export const PendingCountSchema = z.object({ count: z.number().int() });
export type PendingCount = z.infer<typeof PendingCountSchema>;

export type CreateMmrRequestInput =
  | {
      target: 'org';
      orgUserPk: number;
      gameType: number;
      requestedMmr: number;
      screenshot: File;
      note?: string;
    }
  | {
      target: 'league';
      leagueUserPk: number;
      requestedMmr: number;
      screenshot: File;
      note?: string;
    };

export type StaffSetMmrInput =
  | {
      target: 'org';
      orgUserPk: number;
      gameType: number;
      mmr: number;
      screenshot?: File | null;
      note?: string;
    }
  | {
      target: 'league';
      leagueUserPk: number;
      mmr: number;
      screenshot?: File | null;
      note?: string;
    };

function mmrField(gameType: GameTypeValue) {
  const [lo, hi] = GAME_MMR_BOUNDS[gameType] ?? DEFAULT_MMR_BOUNDS;
  const min = Math.max(lo, 1);
  return z.preprocess(
    (v) =>
      v === '' || v === null || (typeof v === 'number' && Number.isNaN(v))
        ? undefined
        : v,
    z.coerce
      .number({ error: 'MMR is required' })
      .int('MMR must be a whole number')
      .min(min, `MMR must be at least ${min}`)
      .max(hi, `MMR must be at most ${hi}`),
  );
}

const noteField = z
  .string()
  .trim()
  .max(TEXT_MAX_LENGTH, `Keep it under ${TEXT_MAX_LENGTH} characters`)
  .default('');

const screenshotField = z.instanceof(File, {
  error: 'A screenshot is required',
});

export function requestMmrFormSchema(gameType: GameTypeValue) {
  return z.object({
    requested_mmr: mmrField(gameType),
    screenshot: screenshotField,
    note: noteField,
  });
}
export type RequestMmrFormSchema = ReturnType<typeof requestMmrFormSchema>;
export type RequestMmrFormValues = z.infer<RequestMmrFormSchema>;

export function staffSetFormSchema(gameType: GameTypeValue) {
  return z.object({
    mmr: mmrField(gameType),
    screenshot: screenshotField.nullable().optional(),
    note: noteField,
  });
}
export type StaffSetFormSchema = ReturnType<typeof staffSetFormSchema>;
export type StaffSetFormValues = z.infer<StaffSetFormSchema>;

export const rejectFormSchema = z.object({
  reason: z
    .string()
    .trim()
    .min(1, 'A reason is required')
    .max(TEXT_MAX_LENGTH, `Keep it under ${TEXT_MAX_LENGTH} characters`),
});
export type RejectFormValues = z.infer<typeof rejectFormSchema>;
