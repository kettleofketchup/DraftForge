import { z } from 'zod';

// dota_lobby's lobby states, plus `requested` and `error`, which DraftForge
// uses before dota_lobby has accepted the create request.
export const LOBBY_STATES = [
  'requested',
  'error',
  'pending',
  'creating',
  'waiting',
  'ready',
  'launching',
  'in_game',
  'post_game',
  'finished',
  'failed',
  'closing',
  'closed',
  'timed_out',
] as const;

export type LobbyState = (typeof LOBBY_STATES)[number];

// Lobby states before the match starts: staff can still close or replace it.
export const PREGAME_LOBBY_STATES: readonly string[] = [
  'requested',
  'pending',
  'creating',
  'waiting',
  'ready',
];

// States in which players can be invited and the match launched.
export const JOINABLE_LOBBY_STATES: readonly string[] = ['waiting', 'ready'];

// Unknown states (a newer dota_lobby) are kept as strings, not rejected.
const LobbyStateSchema = z.string();

/** A list the backend may send as null: parsed as an empty list. */
const nullableList = <T extends z.ZodType>(item: T) =>
  z
    .array(item)
    .nullish()
    .transform((v) => v ?? []);

const LobbyTeamSchema = z.object({ id: z.number(), name: z.string() }).nullable();

export const LobbyPlayerSchema = z.object({
  user_id: z.number(),
  name: z.string(),
  side: z.enum(['radiant', 'dire']),
  team_id: z.number(),
  captain: z.boolean(),
  account_id: z.number().nullable(),
  status: z.string(),
  seat: z.string().nullable().optional(),
  ready: z.boolean(),
  invites_sent: z.number(),
  last_invite_at: z.string().nullable().optional(),
});

export const GameLobbySchema = z.object({
  id: z.number(),
  state: LobbyStateSchema,
  ended: z.boolean(),
  match_id: z.string().nullable(),
  radiant_team: LobbyTeamSchema,
  dire_team: LobbyTeamSchema,
  provisional_winner_side: z.enum(['radiant', 'dire']).nullable(),
  provisional_winner_team_id: z.number().nullable(),
  provisional_outcome_name: z.string().nullable(),
  provisional_scored: z.boolean().nullable(),
  duration_seconds: z.number().nullable(),
  match_started_at: z.string().nullable(),
  match_ended_at: z.string().nullable(),
  updated_at: z.string(),
  // Only for the game's players and tournament staff.
  state_reason: z.string().nullable().optional(),
  trigger: z.string().optional(),
  name: z.string().nullable().optional(),
  game_mode: z.union([z.string(), z.number()]).nullable().optional(),
  region: z.union([z.string(), z.number()]).nullable().optional(),
  launch: z.string().nullable().optional(),
  league_id: z.number().nullable().optional(),
  league_verified: z.boolean().nullable().optional(),
  bot: z.string().nullable().optional(),
  password: z.string().nullable().optional(),
  players: nullableList(LobbyPlayerSchema).optional(),
  pending_invites: nullableList(z.string()).optional(),
  launch_attempts: z.number().optional(),
  last_error_code: z.string().nullable().optional(),
  last_error_detail: z.string().nullable().optional(),
  last_error_at: z.string().nullable().optional(),
  created_at: z.string().optional(),
  ended_at: z.string().nullable().optional(),
});

export const LobbyEligibilitySchema = z.object({
  ok: z.boolean(),
  code: z.string().nullable(),
  details: z
    .object({
      players: nullableList(z.object({ id: z.number(), name: z.string() })).optional(),
    })
    .loose()
    .default({}),
});

export const GameLobbyResponseSchema = z.object({
  game_id: z.number(),
  enabled: z.boolean(),
  mode: z.enum(['off', 'manual', 'auto']),
  can_manage: z.boolean(),
  is_player: z.boolean(),
  lobby: GameLobbySchema.nullable(),
  // Staff only.
  eligibility: LobbyEligibilitySchema.optional(),
  players: nullableList(LobbyPlayerSchema).optional(),
});

export const InviteResultSchema = z.object({
  invited: nullableList(z.number()),
  skipped: nullableList(z.object({ account_id: z.number(), reason: z.string() })),
});

export type GameLobby = z.infer<typeof GameLobbySchema>;
export type GameLobbyResponse = z.infer<typeof GameLobbyResponseSchema>;
export type LobbyPlayer = z.infer<typeof LobbyPlayerSchema>;
export type LobbyEligibility = z.infer<typeof LobbyEligibilitySchema>;
export type InviteResult = z.infer<typeof InviteResultSchema>;
