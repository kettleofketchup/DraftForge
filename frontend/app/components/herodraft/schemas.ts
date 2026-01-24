import { z } from 'zod';

export const DraftTeamCaptainSchema = z.object({
  pk: z.number(),  // Backend uses 'pk' not 'id'
  username: z.string(),
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
  id: z.number(),
  game: z.number(),
  state: z.enum(["waiting_for_captains", "rolling", "choosing", "drafting", "paused", "completed", "abandoned"]),
  roll_winner: DraftTeamSchema.nullable(), // Backend returns full DraftTeam object
  draft_teams: z.array(DraftTeamSchema),
  rounds: z.array(HeroDraftRoundSchema),
  current_round: z.number().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});

// WebSocket message schemas for runtime validation
export const HeroDraftTickSchema = z.object({
  type: z.literal("herodraft_tick"),
  current_round: z.number(),
  active_team_id: z.number().nullable(),
  grace_time_remaining_ms: z.number(),
  // Team IDs for matching reserve times to correct teams
  team_a_id: z.number().nullable(),
  team_a_reserve_ms: z.number(),
  team_b_id: z.number().nullable(),
  team_b_reserve_ms: z.number(),
  draft_state: z.string(),
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
  event_id: z.number().optional(),
  // Backend sends full DraftTeam object via DraftTeamSerializerFull, or null
  draft_team: DraftTeamSchema.nullable().optional(),
  metadata: HeroDraftEventMetadataSchema.optional(),
  draft_state: HeroDraftSchema.optional(),
  timestamp: z.string().optional(),
});

export const InitialStateMessageSchema = z.object({
  type: z.literal("initial_state"),
  draft_state: HeroDraftSchema,
});

// Discriminated union for all WebSocket message types
export const HeroDraftWebSocketMessageSchema = z.discriminatedUnion("type", [
  InitialStateMessageSchema,
  HeroDraftEventSchema,
  HeroDraftTickSchema,
]);
