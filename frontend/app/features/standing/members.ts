import { z } from 'zod';

export const MemberSummarySchema = z.object({
  org_user_pk: z.number(),
  user_pk: z.number(),
  username: z.string(),
  nickname: z.string().nullable(),
  discordNickname: z.string().nullish(),
  guildNickname: z.string().nullish(),
  avatarUrl: z.string().nullable(),
});
export type MemberSummary = z.infer<typeof MemberSummarySchema>;
