// GENERATED FILE - DO NOT EDIT.
// Source: backend/discordbot/permissions/schemas.py
// Regenerate with: just py::gen-discord-permissions-api
import { z } from 'zod';

export const ActionKindSchema = z.enum([
  'signup_create',
  'signup_fallback',
  'announcement',
  'attendance_reminder',
  'profile_reminder',
  'new_event_notice',
  'start_mention',
  'signup_edit',
  'announcement_edit',
  'scheduled_event_create',
  'scheduled_event_update',
  'scheduled_event_delete',
  'mark_interested',
  'signup_reminder_dm',
  'tournament_dm',
  'template_post',
  'admin_channel_post',
]);
export type ActionKind = z.infer<typeof ActionKindSchema>;

export const BlockerSchema = z.object({
  code: z.enum([
    'missing_reference',
    'forum_requires_tag',
    'communication_timeout',
    'role_not_mentionable',
    'role_missing',
    'thread_archived',
    'thread_locked',
    'private_thread_access',
  ]),
  detail: z.union([z.string(), z.null()]),
  role_id: z.union([z.string(), z.null()]),
  missing: z.array(z.string()),
});
export type Blocker = z.infer<typeof BlockerSchema>;

export const DestinationSchema = z.object({
  kind: z.enum(['channel', 'thread', 'guild', 'dm', 'none']),
  channel_id: z.union([z.string(), z.null()]),
  parent_id: z.union([z.string(), z.null()]),
  name: z.union([z.string(), z.null()]),
  channel_type: z.union([z.number().int(), z.null()]),
  source: z.union([
    z.enum([
      'configured',
      'fallback',
      'posted',
      'prospective',
      'guild',
      'recipient',
    ]),
    z.null(),
  ]),
});
export type Destination = z.infer<typeof DestinationSchema>;

export const PermissionCheckInSchema = z
  .object({
    key: z.string().regex(new RegExp('^[a-z0-9][a-z0-9_-]{0,63}$')),
    action: ActionKindSchema,
    channel_id: z.union([
      z.string().regex(new RegExp('^[0-9]{17,20}$')),
      z.null(),
    ]),
    role_ids: z
      .array(z.string().regex(new RegExp('^[0-9]{17,20}$')))
      .max(25)
      .optional(),
    include_rsvp: z.boolean(),
  })
  .strict();
export type PermissionCheckIn = z.infer<typeof PermissionCheckInSchema>;

export const PermissionCheckResultSchema = z.object({
  key: z.string(),
  action: ActionKindSchema,
  status: z.enum([
    'verified',
    'missing_permissions',
    'unconfigured',
    'unknown',
    'unsupported',
    'not_applicable',
  ]),
  destination: DestinationSchema,
  required_all: z.array(z.string()),
  required_any: z.array(z.array(z.string())),
  missing: z.array(z.string()),
  granted: z.union([z.array(z.string()), z.null()]),
  effective_permissions: z.union([z.string(), z.null()]),
  raw_permissions: z.union([z.string(), z.null()]),
  base_granted: z.union([z.array(z.string()), z.null()]),
  bypass: z.union([z.enum(['owner', 'administrator']), z.null()]),
  blockers: z.array(BlockerSchema),
  reason: z.union([
    z.enum([
      'no_server_configured',
      'no_channel_configured',
      'bot_unavailable',
      'credential_unavailable',
      'forbidden_read',
      'resource_unavailable',
      'rate_limited',
      'network_error',
      'malformed_snapshot',
      'pending_signup_post',
      'unsupported_channel_type',
      'unsupported_endpoint',
      'unsupported_signup_transport',
    ]),
    z.null(),
  ]),
  checked_at: z.union([z.string().datetime({ offset: true }), z.null()]),
  expires_at: z.union([z.string().datetime({ offset: true }), z.null()]),
  retry_after_seconds: z.union([z.number().int(), z.null()]),
  refresh_state: z.union([
    z.enum(['fresh', 'cached', 'coalesced', 'throttled']),
    z.null(),
  ]),
});
export type PermissionCheckResult = z.infer<typeof PermissionCheckResultSchema>;

export const PermissionChecksRequestSchema = z
  .object({
    refresh: z.boolean(),
    checks: z.array(PermissionCheckInSchema).min(1).max(20),
  })
  .strict();
export type PermissionChecksRequest = z.infer<
  typeof PermissionChecksRequestSchema
>;

export const PermissionChecksResponseSchema = z.object({
  guild_id: z.union([z.string(), z.null()]),
  checks: z.array(PermissionCheckResultSchema),
});
export type PermissionChecksResponse = z.infer<
  typeof PermissionChecksResponseSchema
>;

export const PermissionChecksApiSchema = z.object({
  request: PermissionChecksRequestSchema,
  response: PermissionChecksResponseSchema,
});
export type PermissionChecksApi = z.infer<typeof PermissionChecksApiSchema>;
