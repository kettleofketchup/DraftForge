import { z } from 'zod';

import { UserSchema } from '../user';

import { DraftOptionsSchema, DraftSchema } from '../teamdraft/schemas';
import { GameSchema } from '../game/schemas';
import { TeamSchema } from '../team';

// Tournament type values (keys from TOURNAMENT_TYPE enum)
export const TOURNAMENT_TYPE_VALUES = ['single_elimination', 'double_elimination', 'swiss'] as const;
export type TournamentTypeValue = typeof TOURNAMENT_TYPE_VALUES[number];

// State values (keys from STATE_CHOICES enum)
export const STATE_VALUES = ['future', 'in_progress', 'past'] as const;

// dota_lobby in-game lobbies: off, created by staff, or created automatically.
export const DOTA_LOBBY_MODE_VALUES = ['off', 'manual', 'auto'] as const;
export const DotaLobbyModeSchema = z.enum(DOTA_LOBBY_MODE_VALUES);
// Who starts the match: staff (or `!start` in lobby chat), or the bot once everyone is ready.
export const DOTA_LOBBY_LAUNCH_VALUES = ['manual', 'auto'] as const;
export const DotaLobbyLaunchSchema = z.enum(DOTA_LOBBY_LAUNCH_VALUES);
export type StateValue = typeof STATE_VALUES[number];

// Common timezone values for tournament scheduling
export const COMMON_TIMEZONES = [
  'UTC',
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'America/Toronto',
  'America/Vancouver',
  'America/Sao_Paulo',
  'Europe/London',
  'Europe/Paris',
  'Europe/Berlin',
  'Europe/Moscow',
  'Asia/Tokyo',
  'Asia/Shanghai',
  'Asia/Singapore',
  'Asia/Seoul',
  'Asia/Kolkata',
  'Australia/Sydney',
  'Australia/Melbourne',
  'Pacific/Auckland',
] as const;

export type TimezoneValue = typeof COMMON_TIMEZONES[number] | string;

// Minimal league info returned by lightweight tournament list endpoint
export const LeagueMinimalSchema = z.object({
  pk: z.number(),
  name: z.string(),
  organization_name: z.string().nullable(),
  organization_id: z.number().nullable().optional(),
  organization_logo: z.string().nullable().optional(),
});

export const SourceEventSchema = z.object({
  id: z.number(),
  name: z.string(),
  event_repeater: z.object({
    id: z.number(),
    name: z.string(),
  }).nullable(),
});

export const TournamentSchema = z.object({
  name: z.string().nullable(),
  date_played: z.string().nullable(), // ISO datetime string
  timezone: z.string().default('UTC'),
  users: z.array(UserSchema).nullable().optional(),
  teams: z.array(TeamSchema).nullable().optional(),
  captains: z.array(UserSchema).nullable().optional(),
  captain_ids: z.array(z.number()).nullable().optional(),
  pk: z.number().nullable(),
  winning_team: z.number().nullable().optional(),
  state: z.enum(STATE_VALUES).nullable(),
  tournament_type: z.enum(TOURNAMENT_TYPE_VALUES).nullable(),
  games: z.array(GameSchema).nullable().optional(),
  user_ids: z.array(z.number()).nullable().optional(),
  team_ids: z.array(z.number()).nullable().optional(),
  draft: DraftSchema.optional(),
  draft_options: DraftOptionsSchema.optional(),
  // League can be number (ID) or object (minimal info from list endpoint)
  league: z.union([z.number(), LeagueMinimalSchema]).nullable().optional(),
  steam_league_id: z.number().nullable().optional(),
  // User count from lightweight list endpoint (instead of full users array)
  user_count: z.number().optional(),
  // Organization PK from the tournament's league
  organization_pk: z.number().nullable().optional(),
  // League PK
  league_pk: z.number().nullable().optional(),
  source_event: SourceEventSchema.nullable().optional(),
  auto_create_hero_drafts: z.boolean().default(false),
  discord_send_draft_link: z.boolean().default(false),
  discord_send_herodraft_link: z.boolean().default(false),
  // dota_lobby in-game lobbies (lobby app)
  dota_lobby_mode: DotaLobbyModeSchema.default('off'),
  dota_lobby_launch: DotaLobbyLaunchSchema.default('manual'),
  dota_lobby_region: z.string().default(''),
  discord_send_lobby_info: z.boolean().default(false),
  // Read-only lobby context (edited through the event settings)
  game_mode: z.string().nullable().optional(),
  lobby_steam_league_id: z.number().nullable().optional(),
});

export const PaginatedTournamentsSchema = z.object({
  count: z.number(),
  next: z.string().nullable(),
  previous: z.string().nullable(),
  results: z.array(TournamentSchema),
});

// Schema for creating a new tournament
export const CreateTournamentSchema = z.object({
  name: z.string().min(1, 'Tournament name is required').max(255),
  tournament_type: z.enum(TOURNAMENT_TYPE_VALUES, {
    message: 'Tournament type is required',
  }),
  date_played: z.string().min(1, 'Date and time is required'),
  timezone: z.string().min(1, 'Timezone is required'),
  league: z.number().nullable().optional(),
  auto_create_hero_drafts: z.boolean().default(false),
  discord_send_draft_link: z.boolean().default(false),
  discord_send_herodraft_link: z.boolean().default(false),
  dota_lobby_mode: DotaLobbyModeSchema.default('off'),
  dota_lobby_launch: DotaLobbyLaunchSchema.default('manual'),
  dota_lobby_region: z.string().max(32, 'Region is at most 32 characters').default(''),
  discord_send_lobby_info: z.boolean().default(false),
});

export type CreateTournamentInput = z.infer<typeof CreateTournamentSchema>;

export const DiscordTournamentLogSchema = z.object({
  id: z.number(),
  category: z.string(),
  notification_type: z.string(),
  message: z.string(),
  recipient_count: z.number(),
  success: z.boolean(),
  created_at: z.string(),
});

export type DiscordTournamentLogEntry = z.infer<typeof DiscordTournamentLogSchema>;
