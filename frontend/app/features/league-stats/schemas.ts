import { z } from 'zod';

const ResultSchema = z.enum(['W', 'L']);

export const StreakSchema = z.object({
  result: ResultSchema,
  count: z.number().int().positive(),
});

export const PlayerLeagueSummarySchema = z.object({
  rank: z.number().int().positive().nullable(),
  top_percent: z.number().int().nullable(),
  games: z.number().int().nonnegative(),
  wins: z.number().int().nonnegative(),
  losses: z.number().int().nonnegative(),
  win_rate: z.number().min(0).max(1),
  bucket: z.number().int().min(0).max(9).nullable(),
  recent: z.array(ResultSchema),
  streak: StreakSchema.nullable(),
});

export const LeagueDistributionSchema = z.object({
  bucket_size: z.number().int().positive(),
  buckets: z.array(
    z.object({
      min: z.number().int(),
      max: z.number().int(),
      count: z.number().int().nonnegative(),
    }),
  ),
});

export const LeaguePlayerSummariesSchema = z.object({
  league_pk: z.number().int(),
  steam_league_id: z.number().int().nullable(),
  min_games: z.number().int().positive(),
  population: z.number().int().nonnegative(),
  players: z.record(z.string(), PlayerLeagueSummarySchema),
  distribution: LeagueDistributionSchema,
});

export const LeagueStatsResponseSchema = z.object({
  user_id: z.number().int(),
  username: z.string(),
  avatar: z.string().nullable(),
  base_mmr: z.number().nullable(),
  league_mmr: z.number().nullable(),
  league_id: z.number().int(),
  games_played: z.number().int(),
  wins: z.number().int(),
  losses: z.number().int(),
  win_rate: z.number(),
  avg_kills: z.number(),
  avg_deaths: z.number(),
  avg_assists: z.number(),
  avg_gpm: z.number(),
  avg_xpm: z.number(),
  mmr_adjustment: z.number(),
  last_updated: z.string(),
});

export type PlayerLeagueSummary = z.infer<typeof PlayerLeagueSummarySchema>;
export type LeagueDistribution = z.infer<typeof LeagueDistributionSchema>;
export type LeaguePlayerSummaries = z.infer<typeof LeaguePlayerSummariesSchema>;
export type LeagueStatsResponse = z.infer<typeof LeagueStatsResponseSchema>;
