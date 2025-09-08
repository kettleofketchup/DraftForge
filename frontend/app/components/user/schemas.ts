import { z } from 'zod';

export const PositionSchema = z.object({
  pk: z.number().optional(),
  carry: z.number().min(0, { message: 'Carry position must be selected.' }),
  mid: z.number().min(0, { message: 'Mid position must be selected.' }),
  offlane: z.number().min(0, { message: 'Offlane position must be selected.' }),
  soft_support: z
    .number()
    .min(0, { message: 'Soft Support position must be selected.' }),
  hard_support: z
    .number()
    .min(0, { message: 'Hard Support position must be selected.' }),
});
export const UserSchema = z.object({
  positions: PositionSchema.optional(),
  username: z.string().min(2).max(100),
  avatarUrl: z.string().url().optional(),
  is_staff: z.boolean().optional(),
  is_superuser: z.boolean().optional(),
  nickname: z.string().min(2).max(100).nullable().optional(),
  mmr: z.number().min(0).nullable().optional(),
  steamid: z.number().min(0).nullable().optional(),
  avatar: z.string().url().nullable().optional(),
  pk: z.number().min(0).optional(),
  discordNickname: z.string().min(2).max(100).nullable().optional(),
  discordId: z.string().min(2).max(100).nullable().optional(),
  guildNickname: z.string().min(2).max(100).nullable().optional().optional(),
});
