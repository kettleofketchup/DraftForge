import { z } from 'zod';

export const TickEnvelopeSchema = z.object({
  draft_state: z.string(),
  server_time: z.string(),
  resuming_until: z.string().nullable().optional(),
});

export type TickEnvelope = z.infer<typeof TickEnvelopeSchema>;
