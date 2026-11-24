import { z } from 'zod';
import { OVERRIDE_REASON_MAX_LENGTH } from '~/components/api/overridesAPI';

export const teamActionSchema = z.object({
  reason: z
    .string()
    .trim()
    .min(3, 'Give a reason (at least 3 characters).')
    .max(OVERRIDE_REASON_MAX_LENGTH),
});
export type TeamActionFormValues = z.infer<typeof teamActionSchema>;

export const subInSchema = teamActionSchema.extend({
  replacing_id: z.number().int().positive().nullable(),
});
export type SubInFormValues = z.infer<typeof subInSchema>;

export const replaceCaptainSchema = teamActionSchema.extend({
  mark_outgoing_dropout: z.boolean().default(true),
});
export type ReplaceCaptainFormValues = z.infer<typeof replaceCaptainSchema>;
