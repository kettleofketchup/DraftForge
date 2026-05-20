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

export const ActiveDraftSchema = z.discriminatedUnion('type', [
  z.object({
    type: z.literal('team_draft'),
    tournament_pk: z.number(),
    draft_state: z.string(),
  }),
  z.object({
    type: z.literal('hero_draft'),
    tournament_pk: z.number(),
    game_pk: z.number(),
    herodraft_pk: z.number(),
    draft_state: z.string(),
  }),
]);

export type ActiveDraftType = z.infer<typeof ActiveDraftSchema>;

export const UserSchema = z.object({
  positions: PositionSchema.optional(),
  // Nullable because ``CustomUser.username`` is ``null=True`` at the model
  // level (Steam-only signups). Form schemas (EditUserSchema) still enforce
  // non-null + length when a user is editing their own profile.
  username: z.string().min(2).max(100).nullable(),
  avatarUrl: z.string().url().optional(),
  is_staff: z.boolean().optional(),
  is_superuser: z.boolean().optional(),
  nickname: z.string().min(2).max(100).nullable().optional(),
  mmr: z.number().min(0).nullable().optional(),
  league_mmr: z.number().min(0).nullable().optional(), // MMR snapshot from LeagueUser
  steam_account_id: z.number().min(0).nullable().optional(), // 32-bit Friend ID (Dotabuff)
  avatar: z.string().url().nullable().optional(),
  orgUserPk: z.number().min(0).optional(), // OrgUser pk (for org-scoped PATCH)
  pk: z.number().min(0).optional(), // User pk (for display)
  discordNickname: z.string().min(2).max(100).nullable().optional(),
  discordId: z.string().min(2).max(100).nullable().optional(),
  guildNickname: z.string().min(2).max(100).nullable().optional(),
  active_drafts: z.array(ActiveDraftSchema).optional(),
  // Role-membership PK lists used by permission hooks to gate global
  // create actions (e.g. Create Tournament) without a follow-up fetch.
  // Backend returns ``[]`` for users with no affiliations — optional
  // here only because older sub-user payloads (team rosters) may not
  // include them.
  admin_organization_ids: z.array(z.number()).optional(),
  staff_organization_ids: z.array(z.number()).optional(),
  admin_league_ids: z.array(z.number()).optional(),
  staff_league_ids: z.array(z.number()).optional(),
});

/**
 * Core user fields for the entity cache.
 * Omits context-scoped fields (id=OrgUser pk, mmr=org MMR, league_mmr)
 * which go into orgData/leagueData on UserEntry.
 * pk is overridden from optional to required.
 */
export const CoreUserSchema = UserSchema.omit({
  orgUserPk: true,
  mmr: true,
  league_mmr: true,
}).extend({ pk: z.number() });

export type CoreUserType = z.infer<typeof CoreUserSchema>;
