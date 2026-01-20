import { z } from 'zod';

export const DraftTeamCaptainSchema = z.object({
  id: z.number(),
  username: z.string(),
  nickname: z.string().nullable(),
  avatar: z.string().nullable(),
});

export const DraftTeamSchema = z.object({
  id: z.number(),
  tournament_team: z.number(),
  captain: DraftTeamCaptainSchema.nullable(),
  team_name: z.string(),
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

export const HeroDraftEventSchema = z.object({
  type: z.literal("herodraft_event"),
  event_type: z.string(),
  draft_team: z.number().nullable().optional(),
  draft_state: HeroDraftSchema.optional(),
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
