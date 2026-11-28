import { z } from 'zod';

// Mirrors backend/events/records.py record_to_json.
export const signupRecordOriginalSchema = z.object({
  signed_up_at: z.string(),
  commitment: z.string(),
  rsvp_class: z.string(),
  means: z.string(),
});

export const signupRecordFinalSchema = z.object({
  status: z.string(),
  commitment: z.string(),
  rsvp_class: z.string(),
  signed_up_at: z.string().nullable(),
  line_seq: z.number().nullable(),
});

export const signupRecordSchema = z.object({
  event_id: z.number(),
  event_name: z.string(),
  scheduled_at: z.string().nullable(),
  event_state: z.string(),
  series_id: z.number().nullable(),
  user_id: z.number().nullable(),
  discord_id: z.string().nullable(),
  original: signupRecordOriginalSchema.nullable(),
  final: signupRecordFinalSchema.nullable(),
  withdrawn_at: z.string().nullable(),
  change_count: z.number(),
  last_changed_at: z.string(),
});

export const signupRecordsResponseSchema = z.object({
  organization: z.number(),
  count: z.number(),
  results: z.array(signupRecordSchema),
});

export const SIGNUP_RECORDS_TOO_MANY = 'too_many_records';

export type SignupRecord = z.infer<typeof signupRecordSchema>;
export type SignupRecordsResponse = z.infer<typeof signupRecordsResponseSchema>;
export type SignupRecordsFilters = {
  since?: string;
  until?: string;
  series?: number;
  event?: number;
  user?: number;
};
