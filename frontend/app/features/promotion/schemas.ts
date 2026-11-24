import { z } from 'zod';

export const MAX_TEMPLATE_BODY = 2000;
export const MAX_TEMPLATE_NAME = 100;
export const DISCORD_DM_LIMIT = 2000;
export const MAX_SEND_TEXT = 4000;
export const DEFAULT_POOL_N = 3;
export const MAX_POOL_N = 10;
export const DEFAULT_DAYS = 30;
export const DAYS_OPTIONS: readonly number[] = [7, 14, 30, 90];

export const CANDIDATE_SOURCES = ['recent', 'active', 'discord'] as const;
export type CandidateSource = (typeof CANDIDATE_SOURCES)[number];
export const PROMOTABLE_STATES: readonly string[] = [
  'upcoming',
  'signups_open',
];

export const PromoTemplateSchema = z.object({
  id: z.number(),
  name: z.string(),
  body: z.string(),
  updated_at: z.string(),
  warnings: z.array(z.string()).optional(),
});
export type PromoTemplate = z.infer<typeof PromoTemplateSchema>;

export const PromoEventSchema = z.object({
  id: z.number(),
  name: z.string(),
  scheduled_at: z.string(),
  ends_at: z.string().nullable(),
  state: z.string(),
  signups_open_at: z.string().nullable(),
  game_type: z.number(),
});
export type PromoEvent = z.infer<typeof PromoEventSchema>;

export const LastMessagedSchema = z.object({
  send_id: z.number(),
  by: z.string().nullable(),
  sent_at: z.string(),
  can_undo: z.boolean(),
});
export type LastMessaged = z.infer<typeof LastMessagedSchema>;

export const CandidateRowSchema = z.object({
  user_pk: z.number().nullable(),
  username: z.string(),
  nickname: z.string().nullable(),
  discordUsername: z.string().nullable(),
  discordNickname: z.string().nullish(),
  guildNickname: z.string().nullish(),
  discordId: z.string().nullable(),
  avatarUrl: z.string().nullable(),
  /** The org's MMR for the event's game; null when unset or no account. */
  mmr: z.number().nullable(),
  recent_count: z.number().nullable(),
  last_active_at: z.string().nullish(),
  discord_joined_at: z.string().nullish(),
  last_messaged: LastMessagedSchema.nullable(),
  earning_send_exists: z.boolean(),
  signed_up: z.boolean(),
});
export type CandidateRow = z.infer<typeof CandidateRowSchema>;
/** A candidate with a DraftForge account, the only kind a message can be recorded for. */
export type LinkedCandidate = CandidateRow & { user_pk: number };

export function isLinked(row: CandidateRow): row is LinkedCandidate {
  return row.user_pk != null;
}

export const CandidatesResponseSchema = z.object({
  source: z.enum(CANDIDATE_SOURCES),
  n: z.number(),
  days: z.number(),
  game_type: z.number(),
  min_mmr: z.number().nullable(),
  max_mmr: z.number().nullable(),
  rows: z.array(CandidateRowSchema),
});
export type CandidatesResponse = z.infer<typeof CandidatesResponseSchema>;

export interface CandidateFilters {
  source: CandidateSource;
  n: number;
  days: number;
  hideSignedUp: boolean;
  hideMessaged: boolean;
  q: string;
  minMmr: number | null;
  maxMmr: number | null;
}

export const DEFAULT_CANDIDATE_FILTERS: CandidateFilters = {
  source: 'recent',
  n: DEFAULT_POOL_N,
  days: DEFAULT_DAYS,
  hideSignedUp: true,
  hideMessaged: true,
  q: '',
  minMmr: null,
  maxMmr: null,
};

export const RenderResponseSchema = z.object({
  text: z.string(),
  warnings: z.array(z.string()),
  will_earn: z.boolean(),
});
export type RenderResponse = z.infer<typeof RenderResponseSchema>;

export interface RenderRequest {
  template_id: number;
  recipient_id: number;
}

export const PromoSendResultSchema = z.object({
  id: z.number(),
  earns_points: z.boolean(),
  points_awarded: z.number().nullable(),
  sent_at: z.string(),
});
export type PromoSendResult = z.infer<typeof PromoSendResultSchema>;

export const promoSendSchema = z.object({
  text: z
    .string()
    .max(MAX_SEND_TEXT, `At most ${MAX_SEND_TEXT} characters`)
    .refine((value) => value.trim().length > 0, 'Message is empty'),
});
export type PromoSendForm = z.infer<typeof promoSendSchema>;

export interface PromoSendInput {
  template_id: number | null;
  recipient_id: number;
  text: string;
}

export const promoTemplateFormSchema = z.object({
  name: z.string().trim().min(1, 'Name is required').max(MAX_TEMPLATE_NAME),
  body: z
    .string()
    .max(MAX_TEMPLATE_BODY, `At most ${MAX_TEMPLATE_BODY} characters`)
    .refine((value) => value.trim().length > 0, 'Body is required'),
});
export type PromoTemplateForm = z.infer<typeof promoTemplateFormSchema>;
