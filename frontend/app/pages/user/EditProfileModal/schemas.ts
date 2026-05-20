import { z } from 'zod';

export const BaseProfileFormSchema = z.object({
  nickname: z.string().min(0).max(100).nullable().optional(),
  avatar: z.string().url().nullable().optional().or(z.literal('')),
});

export type BaseProfileFormValues = z.infer<typeof BaseProfileFormSchema>;
