import { z } from 'zod';

// Dota positions use a 0-5 self-rating scale. NESTED under `positions` to match
// PositionFormFields' `name="positions.carry"` field bindings. z.coerce because
// the Select onValueChange already passes Number(), but coercion keeps the
// schema robust to string-valued defaults.
export const PositionFieldSchema = z.coerce.number().int().min(0).max(5);
export const DotaProfileFormSchema = z.object({
  positions: z.object({
    carry: PositionFieldSchema,
    mid: PositionFieldSchema,
    offlane: PositionFieldSchema,
    soft_support: PositionFieldSchema,
    hard_support: PositionFieldSchema,
  }),
});

export type DotaProfileFormValues = z.infer<typeof DotaProfileFormSchema>;

// Deadlock rank is a free-text rank label (e.g. "Archon") with an optional
// verification date. Both nullable/optional — clearing them is valid.
export const DeadlockProfileFormSchema = z.object({
  rank: z.string().max(64).nullable().optional(),
  rank_date: z.string().nullable().optional(),
});

export type DeadlockProfileFormValues = z.infer<
  typeof DeadlockProfileFormSchema
>;
