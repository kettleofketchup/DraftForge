import { z } from 'zod';

export const MAX_TEMPLATE_BODY = 2000;
export const MAX_TEMPLATE_NAME = 100;
export const DISCORD_DM_LIMIT = 2000;
export const MAX_SEND_TEXT = 4000;
export const DEFAULT_POOL_N = 3;
export const MAX_POOL_N = 10;
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
  user_pk: z.number(),
  username: z.string(),
  nickname: z.string().nullable(),
  discordUsername: z.string().nullable(),
  discordId: z.string().nullable(),
  avatarUrl: z.string().nullable(),
  recent_count: z.number(),
  last_messaged: LastMessagedSchema.nullable(),
  earning_send_exists: z.boolean(),
  signed_up: z.boolean(),
});
export type CandidateRow = z.infer<typeof CandidateRowSchema>;

export const CandidatesResponseSchema = z.object({
  n: z.number(),
  rows: z.array(CandidateRowSchema),
});
export type CandidatesResponse = z.infer<typeof CandidatesResponseSchema>;

export interface CandidateFilters {
  n: number;
  hideSignedUp: boolean;
  hideMessaged: boolean;
  q: string;
}

export const DEFAULT_CANDIDATE_FILTERS: CandidateFilters = {
  n: DEFAULT_POOL_N,
  hideSignedUp: true,
  hideMessaged: true,
  q: '',
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
