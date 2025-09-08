import { z } from 'zod';
import { DraftRoundSchema, DraftSchema } from './schemas';
export type DraftType = z.infer<typeof DraftSchema>;
export type DraftRoundType = z.infer<typeof DraftRoundSchema>;
