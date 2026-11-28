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

// Hand-written from backend/org/integration/ticks.py (_contact): a contact
// recorded externally and imported here. It is a recorded claim, not proof the
// DM was delivered, and it can never be undone from DraftForge.
export const ExternalContactSchema = z.object({
  source: z.literal('contact_log'),
  recorded_at: z.string(),
  delivery_verified: z.boolean(),
  can_undo: z.boolean(),
});
export type ExternalContact = z.infer<typeof ExternalContactSchema>;

export const CONTACT_SYNC_WARNINGS = ['history_may_be_incomplete'] as const;

// Hand-written from backend/org/integration/contacts.py (contact_sync_status).
// last_receipt_imported_at is when the newest receipt arrived, not proof the
// imported history is complete.
export const ContactSyncSchema = z.object({
  configured: z.boolean(),
  last_receipt_imported_at: z.string().nullable(),
  warning: z.enum(CONTACT_SYNC_WARNINGS).nullable(),
});
export type ContactSync = z.infer<typeof ContactSyncSchema>;

export const EXTERNAL_WRITEBACK_STATES = [
  'pending',
  'in_flight',
  'retry',
  'paused',
  'backlog_held',
  'reconciliation_required',
  'applied',
  'canceled',
] as const;
export type ExternalWritebackState = (typeof EXTERNAL_WRITEBACK_STATES)[number];

// Hand-written from backend/org/integration/outbox.py (outbox_summary). The
// state of writing one local send to the external contact log; only
// `applied` means it is stored there.
export const ExternalWritebackSchema = z.object({
  state: z.enum(EXTERNAL_WRITEBACK_STATES).nullable(),
  reason: z.string().nullable(),
  delivery_id: z.string().nullable(),
});
export type ExternalWriteback = z.infer<typeof ExternalWritebackSchema>;

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
  /** A local send or an imported external contact exists for this event. */
  contact_recorded: z.boolean(),
  external_contact: ExternalContactSchema.nullable(),
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
  contact_sync: ContactSyncSchema,
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
  writeback: ExternalWritebackSchema,
});
export type PromoSendResult = z.infer<typeof PromoSendResultSchema>;

/** Undo removes the local send; its external receipt stays and is reported. */
export const PromoUndoResultSchema = z.object({
  writeback: ExternalWritebackSchema,
});
export type PromoUndoResult = z.infer<typeof PromoUndoResultSchema>;

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
