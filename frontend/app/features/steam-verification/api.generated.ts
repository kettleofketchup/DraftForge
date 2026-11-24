// GENERATED FILE - DO NOT EDIT.
// Source: backend/app/steam_verification_schemas.py
// Regenerate with: just py::gen-steam-verification
import { z } from 'zod';

export const SteamVerificationInSchema = z
  .object({ verified: z.boolean(), steam_account_id: z.number().int().gte(1) })
  .strict();
export type SteamVerificationIn = z.infer<typeof SteamVerificationInSchema>;

export const SteamVerificationOutSchema = z.object({
  steam_account_id: z.union([z.number().int(), z.null()]),
  steam_account_verified: z.boolean(),
  steam_account_verified_at: z.union([
    z.string().datetime({ offset: true }),
    z.null(),
  ]),
  steam_account_verified_org_name: z.union([z.string(), z.null()]),
  steam_account_exists_checked: z.boolean(),
  steam_profile_url: z.union([z.string(), z.null()]),
  dotabuff_url: z.union([z.string(), z.null()]),
  can_verify: z.boolean(),
});
export type SteamVerificationOut = z.infer<typeof SteamVerificationOutSchema>;

export const SteamVerificationApiSchema = z.object({
  verification: SteamVerificationOutSchema,
  verification_update: SteamVerificationInSchema,
});
export type SteamVerificationApi = z.infer<typeof SteamVerificationApiSchema>;
