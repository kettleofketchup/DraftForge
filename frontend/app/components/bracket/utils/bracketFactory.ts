import type { TeamType } from '~/components/tournament/types';
import type { BracketMatch, SeedingMethod } from '../types';
import { generateDoubleElimination } from './doubleElimination';
import { applySeedingMethod, applyTeamsToFirstRound } from './seeding';

export type BracketType = 'double_elimination' | 'swiss';

export interface BracketResult {
  type: BracketType;
  matches: BracketMatch[];
}

/**
 * Factory function to generate bracket based on tournament type
 */
export function generateBracket(
  type: BracketType,
  teams: TeamType[],
  seedingMethod: SeedingMethod = 'mmr_total'
): BracketResult {
  switch (type) {
    case 'double_elimination': {
      // Seed teams first
      const seededTeams = applySeedingMethod(teams, seedingMethod);

      // Generate bracket structure
      const matches = generateDoubleElimination(seededTeams);

      // Apply teams to first round
      const matchesWithTeams = applyTeamsToFirstRound(matches, seededTeams);

      return {
        type: 'double_elimination',
        matches: matchesWithTeams,
      };
    }

    case 'swiss':
      // Stub for Swiss bracket - to be implemented later
      console.warn('Swiss bracket generation not yet implemented');
      return {
        type: 'swiss',
        matches: [],
      };

    default:
      throw new Error(`Unknown bracket type: ${type}`);
  }
}

/**
 * Reseed an existing bracket with a new seeding method
 */
export function reseedBracket(
  matches: BracketMatch[],
  teams: TeamType[],
  seedingMethod: SeedingMethod
): BracketMatch[] {
  // Clear existing team assignments
  const clearedMatches = matches.map((match) => ({
    ...match,
    radiantTeam: undefined,
    direTeam: undefined,
    winner: undefined,
    status: 'pending' as const,
  }));

  // Apply new seeding
  const seededTeams = applySeedingMethod(teams, seedingMethod);
  return applyTeamsToFirstRound(clearedMatches, seededTeams);
}
