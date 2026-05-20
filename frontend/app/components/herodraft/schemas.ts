import { z } from 'zod';

export const DraftTeamCaptainSchema = z.object({
  pk: z.number(),  // Backend uses 'pk' not 'id'
  // ``CustomUser.username`` is nullable (Steam-only signups don't pick one),
  // so the schema has to accept null too. Render sites fall back to
  // nickname / '?' via DisplayName.
  username: z.string().nullable(),
  nickname: z.string().nullable(),
  avatar: z.string().nullable(),
  avatarUrl: z.string().nullable().optional(),
  discordId: z.string().nullable().optional(),
});

export const DraftTeamSchema = z.object({
  id: z.number(),
  tournament_team: z.number(),
  captain: DraftTeamCaptainSchema.nullable(),
  team_name: z.string(),
  members: z.array(DraftTeamCaptainSchema).optional().default([]),
  is_first_pick: z.boolean().nullable(),
  is_radiant: z.boolean().nullable(),
  reserve_time_remaining: z.number(), // milliseconds
  is_ready: z.boolean(),
  is_connected: z.boolean(),
});

export const HeroDraftRoundSchema = z.object({
  id: z.number(),
  round_number: z.number(),
  action_type: z.enum(["ban", "pick"]),
  hero_id: z.number().nullable(),
  state: z.enum(["planned", "active", "completed"]),
  grace_time_ms: z.number(),
  started_at: z.string().nullable(),
  completed_at: z.string().nullable(),
  draft_team: z.number(),
  team_name: z.string().nullable(),
});

export const HeroDraftSchema = z.object({
  pk: z.number().optional(), // Backend sends both pk and id (same value)
  id: z.number(),
  game: z.number(),
  tournament_id: z.number().nullable().optional(), // Tournament for "Return to Bracket" navigation
  state: z.enum(["waiting_for_captains", "rolling", "choosing", "drafting", "paused", "resuming", "completed", "abandoned"]),
  roll_winner: DraftTeamSchema.nullable(), // Backend returns full DraftTeam object
  draft_teams: z.array(DraftTeamSchema),
  rounds: z.array(HeroDraftRoundSchema),
  current_round: z.number().nullable(),
  is_manual_pause: z.boolean().optional(), // True if paused manually by captain/staff
  created_at: z.string(),
  updated_at: z.string(),
});

// Tick messages carry ANCHORS (timestamps + durations), not computed
// remainders. The client uses `server_time` to derive a clock offset
// and renders countdowns locally via requestAnimationFrame.
export const HeroDraftTickSchema = z.object({
  type: z.literal("herodraft_tick"),
  draft_state: z.string(),
  // Clock anchor — present on every tick regardless of state
  server_time: z.string(),
  // DRAFTING anchors
  current_round: z.number().nullable().optional(),
  active_team_id: z.number().nullable().optional(),
  round_started_at: z.string().nullable().optional(),
  round_grace_time_ms: z.number().nullable().optional(),
  team_a_id: z.number().nullable().optional(),
  team_a_reserve_ms: z.number().nullable().optional(),
  team_b_id: z.number().nullable().optional(),
  team_b_reserve_ms: z.number().nullable().optional(),
  // RESUMING anchor
  resuming_until: z.string().nullable().optional(),
});

// Metadata schema for hero_selected events
export const HeroDraftEventMetadataSchema = z.object({
  hero_id: z.number().optional(),
  action_type: z.enum(["ban", "pick"]).optional(),
  round_number: z.number().optional(),
  time_elapsed_ms: z.number().optional(),
  reserve_used_ms: z.number().optional(),
}).passthrough();  // Allow additional fields

export const HeroDraftEventSchema = z.object({
  type: z.literal("herodraft_event"),
  event_type: z.string(),
  // Use .nullable().optional() to accept null, undefined, or actual values
  // Backend may send null for missing fields via .get() default behavior
  event_id: z.number().nullable().optional(),
  // Backend sends full DraftTeam object via DraftTeamSerializerFull, or null
  draft_team: DraftTeamSchema.nullable().optional(),
  metadata: HeroDraftEventMetadataSchema.nullable().optional(),
  draft_state: HeroDraftSchema.nullable().optional(),
  timestamp: z.string().nullable().optional(),
});

export const InitialStateMessageSchema = z.object({
  type: z.literal("initial_state"),
  draft_state: HeroDraftSchema,
});

export const HeroDraftKickedSchema = z.object({
  type: z.literal("herodraft_kicked"),
  reason: z.string(),
});

export const PingSchema = z.object({
  type: z.literal("ping"),
});

// Discriminated union for all WebSocket message types
export const HeroDraftWebSocketMessageSchema = z.discriminatedUnion("type", [
  InitialStateMessageSchema,
  HeroDraftEventSchema,
  HeroDraftTickSchema,
  HeroDraftKickedSchema,
  PingSchema,
]);
