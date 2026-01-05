// frontend/app/lib/dota/schemas.ts
import { z } from 'zod';

export const PlayerMatchStatsSchema = z.object({
  steam_id: z.number(),
  username: z.string().nullable(),
  player_slot: z.number(),
  hero_id: z.number(),
  kills: z.number(),
  deaths: z.number(),
  assists: z.number(),
  gold_per_min: z.number(),
  xp_per_min: z.number(),
  last_hits: z.number(),
  denies: z.number(),
  hero_damage: z.number(),
  tower_damage: z.number(),
  hero_healing: z.number(),
});

export const MatchDetailSchema = z.object({
  match_id: z.number(),
  radiant_win: z.boolean(),
  duration: z.number(),
  start_time: z.number(),
  game_mode: z.number(),
  lobby_type: z.number(),
  players: z.array(PlayerMatchStatsSchema),
});

export type PlayerMatchStats = z.infer<typeof PlayerMatchStatsSchema>;
export type MatchDetail = z.infer<typeof MatchDetailSchema>;
