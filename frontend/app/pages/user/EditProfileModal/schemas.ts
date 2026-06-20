import { z } from 'zod';

// Avatar is synced server-side from Discord (avatar hash, not URL). Users
// don't edit it — the field stays on BaseUserProfile and is updated by
// the Discord avatar refresh background task. If a future ticket adds
// user-uploaded avatars, the schema would gain `avatar` here.
export const BaseProfileFormSchema = z.object({
  nickname: z.string().min(0).max(100).nullable().optional(),
});

export type BaseProfileFormValues = z.infer<typeof BaseProfileFormSchema>;

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
