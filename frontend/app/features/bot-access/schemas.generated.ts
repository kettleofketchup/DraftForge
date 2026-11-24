// GENERATED FILE - DO NOT EDIT.
// Source: backend/lobby/bot_access/schemas.py
// Regenerate with: just py::gen-bot-access-api
import { z } from 'zod';

export const BotIdentitySchema = z.object({
  kind: z.string(),
  value: z.string(),
  profile_url: z.union([z.string().regex(new RegExp('^https://')), z.null()]),
});
export type BotIdentity = z.infer<typeof BotIdentitySchema>;

export const BotAccessRowSchema = z.object({
  position: z.number().int(),
  identity: z.union([BotIdentitySchema, z.null()]),
  status: z.union([
    z.enum(['available', 'busy', 'connecting', 'offline', 'unknown']),
    z.null(),
  ]),
  access: z.enum(['verified', 'unverified', 'missing', 'unknown']),
  access_note: z.union([
    z.enum(['allowed_unverified', 'not_rechecked']),
    z.null(),
  ]),
  access_checked_at: z.union([z.string().datetime({ offset: true }), z.null()]),
  refresh: z.union([z.enum(['ok', 'failed', 'not_ready']), z.null()]),
});
export type BotAccessRow = z.infer<typeof BotAccessRowSchema>;

export const PlatformLinkSchema = z.object({
  kind: z.literal('league_admin_portal'),
  url: z.string().regex(new RegExp('^https://')),
});
export type PlatformLink = z.infer<typeof PlatformLinkSchema>;

export const ServiceStateSchema = z.object({
  status: z.enum([
    'ok',
    'unsupported',
    'disabled',
    'not_configured',
    'league_not_linked',
    'unavailable',
    'error',
  ]),
  code: z.union([z.string(), z.null()]),
  retryable: z.boolean(),
});
export type ServiceState = z.infer<typeof ServiceStateSchema>;

export const BotAccessSnapshotSchema = z.object({
  game_type: z.union([z.number().int(), z.null()]),
  supported: z.boolean(),
  provider: z.string(),
  external_league_id: z.union([z.string(), z.null()]),
  service: ServiceStateSchema,
  bots: z.array(BotAccessRowSchema),
  held_count: z.number().int(),
  league_link: z.union([PlatformLinkSchema, z.null()]),
  refresh_outcome: z.union([
    z.enum(['ok', 'unavailable', 'timed_out', 'not_supported_upstream']),
    z.null(),
  ]),
  roster: z.enum(['all', 'holders']),
  checked_at: z.string().datetime({ offset: true }),
});
export type BotAccessSnapshot = z.infer<typeof BotAccessSnapshotSchema>;

export const BotAccessApiSchema = z.object({
  snapshot: BotAccessSnapshotSchema,
});
export type BotAccessApi = z.infer<typeof BotAccessApiSchema>;
