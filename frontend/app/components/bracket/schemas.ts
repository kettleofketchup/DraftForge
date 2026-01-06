import { z } from 'zod';

// Match status enum
export const MatchStatusSchema = z.enum(['pending', 'live', 'completed']);

// Bracket section enum
export const BracketSectionSchema = z.enum(['winners', 'losers', 'grand_finals', 'swiss']);

// Elimination type enum
export const EliminationTypeSchema = z.enum(['single', 'double', 'swiss']);

// Seeding method enum
export const SeedingMethodSchema = z.enum(['random', 'mmr_total', 'captain_mmr', 'manual']);

// Single bracket match (matches backend API response)
export const BracketMatchSchema = z.object({
  pk: z.number(),                      // Backend Game.pk (primary key)
  round: z.number().min(1),
  position: z.number().min(0),
  bracket_type: BracketSectionSchema,
  elimination_type: EliminationTypeSchema.optional(),
  radiant_team: z.any().optional(),    // TeamType from API
  dire_team: z.any().optional(),       // TeamType from API
  winning_team: z.any().optional(),    // TeamType from API
  status: MatchStatusSchema,
  gameid: z.number().optional(),       // Steam match ID
  next_game: z.number().nullable().optional(),    // FK to next game for winner
  next_game_slot: z.enum(['radiant', 'dire']).nullable().optional(),
  loser_next_game: z.number().nullable().optional(),    // FK to next game for loser
  loser_next_game_slot: z.enum(['radiant', 'dire']).nullable().optional(),
  swiss_record_wins: z.number().optional(),
  swiss_record_losses: z.number().optional(),
});

// API response for bracket
export const BracketResponseSchema = z.object({
  tournamentId: z.number(),
  matches: z.array(BracketMatchSchema),
});

// Generate bracket request
export const GenerateBracketRequestSchema = z.object({
  seeding_method: SeedingMethodSchema,
});

// Save bracket request
export const SaveBracketRequestSchema = z.object({
  matches: z.array(BracketMatchSchema),
});

// Type exports
export type BracketMatch = z.infer<typeof BracketMatchSchema>;
export type BracketResponse = z.infer<typeof BracketResponseSchema>;
export type GenerateBracketRequest = z.infer<typeof GenerateBracketRequestSchema>;
export type SaveBracketRequest = z.infer<typeof SaveBracketRequestSchema>;
