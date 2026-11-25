// GENERATED FILE - DO NOT EDIT.
// Source: backend/org/mmr_requests/schemas.py
// Regenerate with: just py::gen-mmr-summary-types
import { z } from 'zod';

export const LastDecisionSchema = z.object({
  id: z.number().int(),
  status: z.enum(['approved', 'rejected', 'superseded']),
  decided_mmr: z.union([z.number().int(), z.null()]),
  rejection_reason: z.string(),
  reviewed_at: z.union([z.string().datetime({ offset: true }), z.null()]),
});
export type LastDecision = z.infer<typeof LastDecisionSchema>;

export const LeagueRefSchema = z.object({
  pk: z.number().int(),
  name: z.string(),
});
export type LeagueRef = z.infer<typeof LeagueRefSchema>;

export const OrgRefSchema = z.object({
  pk: z.number().int(),
  name: z.string(),
  logo: z.union([z.string(), z.null()]),
});
export type OrgRef = z.infer<typeof OrgRefSchema>;

export const PendingRequestRefSchema = z.object({
  id: z.number().int(),
  requested_mmr: z.number().int(),
  created_at: z.string().datetime({ offset: true }),
});
export type PendingRequestRef = z.infer<typeof PendingRequestRefSchema>;

export const UserRefSchema = z.object({
  pk: z.number().int(),
  username: z.string(),
});
export type UserRef = z.infer<typeof UserRefSchema>;

export const GameMmrEntrySchema = z.object({
  game_type: z.number().int(),
  mmr: z.number().int(),
  verified: z.boolean(),
  verified_at: z.union([z.string().datetime({ offset: true }), z.null()]),
  verified_by: z.union([UserRefSchema, z.null()]),
  legacy_verified: z.boolean(),
  pending_request: z.union([PendingRequestRefSchema, z.null()]),
  last_decision: z.union([LastDecisionSchema, z.null()]),
});
export type GameMmrEntry = z.infer<typeof GameMmrEntrySchema>;

export const LeagueMmrEntrySchema = z.object({
  league: LeagueRefSchema,
  organization_pk: z.union([z.number().int(), z.null()]),
  league_user_pk: z.union([z.number().int(), z.null()]),
  mmr: z.number().int(),
  verified: z.boolean(),
  verified_at: z.union([z.string().datetime({ offset: true }), z.null()]),
  verified_by: z.union([UserRefSchema, z.null()]),
  pending_request: z.union([PendingRequestRefSchema, z.null()]),
  last_decision: z.union([LastDecisionSchema, z.null()]),
});
export type LeagueMmrEntry = z.infer<typeof LeagueMmrEntrySchema>;

export const OrgMmrEntrySchema = z.object({
  organization: OrgRefSchema,
  org_user_pk: z.union([z.number().int(), z.null()]),
  game_mmrs: z.array(GameMmrEntrySchema),
});
export type OrgMmrEntry = z.infer<typeof OrgMmrEntrySchema>;

export const UserMmrSummarySchema = z.object({
  user_pk: z.number().int(),
  orgs: z.array(OrgMmrEntrySchema),
  leagues: z.array(LeagueMmrEntrySchema),
});
export type UserMmrSummary = z.infer<typeof UserMmrSummarySchema>;
