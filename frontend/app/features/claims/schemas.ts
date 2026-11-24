import { z } from 'zod';

export const CLAIM_STATUSES = ['pending', 'approved', 'rejected'] as const;
export const ClaimStatusSchema = z.enum(CLAIM_STATUSES);
export type ClaimStatus = z.infer<typeof ClaimStatusSchema>;

// backend/org/serializers.py ProfileClaimRequestSerializer
export const ProfileClaimRequestSchema = z.object({
  id: z.number(),
  claimer: z.number(),
  claimer_username: z.string(),
  claimer_discord_id: z.string().nullable(),
  claimer_avatar: z.string().nullable(),
  // null once an approved claim merges the target profile away
  target_user: z.number().nullable(),
  target_nickname: z.string().nullable(),
  target_username: z.string().nullable().optional(),
  target_discordNickname: z.string().nullable().optional(),
  target_steamid: z.number().nullable(),
  target_mmr: z.number().nullable(),
  target_game_mmrs: z.record(z.string(), z.number()).nullable().optional(),
  organization: z.number(),
  organization_name: z.string(),
  status: ClaimStatusSchema,
  reviewed_by: z.number().nullable(),
  reviewed_by_username: z.string().nullable(),
  rejection_reason: z.string(),
  created_at: z.string(),
  reviewed_at: z.string().nullable(),
});
export type ProfileClaimRequest = z.infer<typeof ProfileClaimRequestSchema>;
