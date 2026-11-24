import { z } from 'zod';

// Mirrors backend/events/serializers.py SignupLedgerEntrySerializer.
export const SIGNUP_LEDGER_ACTIONS = [
  'backfilled',
  'signed_up',
  'resigned_up',
  'switched_commitment',
  'approved',
  'confirmed',
  'unconfirmed',
  'rejected',
  'withdrew',
  'declined',
  'waitlisted',
  'promoted',
  'demoted',
  'reinstated',
  'voided_withdrawal',
  'transferred_out',
  'transferred_in',
  'swapped',
  'staff_added',
  'account_merged',
  'moved_event',
  'event_cancelled',
] as const;

export type SignupLedgerAction = (typeof SIGNUP_LEDGER_ACTIONS)[number];

export const signupLedgerActionSchema = z
  .enum(SIGNUP_LEDGER_ACTIONS)
  .or(z.string());

export const signupMeansSchema = z
  .enum(['web', 'discord_button', 'discord_reaction', 'system'])
  .or(z.string());

export const actorRoleSchema = z
  .enum(['member', 'staff', 'system'])
  .or(z.string());

export const signupSnapshotSchema = z.object({
  status: z.string(),
  commitment: z.string(),
  rsvp_class: z.string(),
  signed_up_at: z.string().nullable(),
  line_seq: z.number().nullable(),
  waitlist_position: z.number().nullable(),
  event_team_id: z.number().nullable(),
  extra: z.record(z.string(), z.unknown()),
});

const historyUserFields = {
  user_id: z.number().nullable(),
  username: z.string().nullable(),
  nickname: z.string().nullable(),
  discordNickname: z.string().nullable(),
  guildNickname: z.string().nullable(),
  avatarUrl: z.string().nullable(),
};

export const historySubjectSchema = z.object({
  ...historyUserFields,
  discord_id: z.string().nullable(),
});

export const historyActorSchema = z.object({
  ...historyUserFields,
  role: actorRoleSchema,
});

export const signupHistoryEntrySchema = z.object({
  id: z.number(),
  occurred_at: z.string(),
  action: signupLedgerActionSchema,
  subject: historySubjectSchema,
  actor: historyActorSchema,
  means: signupMeansSchema,
  on_behalf: z.boolean(),
  reason: z.string(),
  before: signupSnapshotSchema.nullable(),
  after: signupSnapshotSchema.nullable(),
  rules_overridden: z.array(z.string()),
  caused_by: z.number().nullable(),
});

export const signupHistoryPageSchema = z.object({
  count: z.number(),
  next: z.string().nullable(),
  previous: z.string().nullable(),
  results: z.array(signupHistoryEntrySchema),
});

export type SignupSnapshot = z.infer<typeof signupSnapshotSchema>;
export type HistorySubject = z.infer<typeof historySubjectSchema>;
export type HistoryActor = z.infer<typeof historyActorSchema>;
export type SignupHistoryEntry = z.infer<typeof signupHistoryEntrySchema>;
export type SignupHistoryPage = z.infer<typeof signupHistoryPageSchema>;
