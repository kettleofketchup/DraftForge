import { z } from 'zod';

// Avatar is synced server-side from Discord (avatar hash, not URL). Users
// don't edit it — the field stays on BaseUserProfile and is updated by
// the Discord avatar refresh background task. If a future ticket adds
// user-uploaded avatars, the schema would gain `avatar` here.
export const BaseProfileFormSchema = z.object({
  nickname: z.string().min(0).max(100).nullable().optional(),
});

export type BaseProfileFormValues = z.infer<typeof BaseProfileFormSchema>;
