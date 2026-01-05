import type { TeamType } from '~/components/tournament/types';
import type { BracketMatch, SeedingMethod } from '../types';

/**
 * Get total MMR for a team (sum of all members)
 */
export function getTotalMMR(team: TeamType): number {
  const captainMMR = team.captain?.mmr ?? 0;
  const membersMMR = team.members?.reduce((sum, m) => sum + (m.mmr ?? 0), 0) ?? 0;
  return captainMMR + membersMMR;
}

/**
 * Sort teams by total MMR (highest first)
 */
export function seedByMMR(teams: TeamType[]): TeamType[] {
  return [...teams].sort((a, b) => getTotalMMR(b) - getTotalMMR(a));
}

/**
 * Sort teams by captain MMR (highest first)
 */
export function seedByCaptainMMR(teams: TeamType[]): TeamType[] {
  return [...teams].sort((a, b) => (b.captain?.mmr ?? 0) - (a.captain?.mmr ?? 0));
}

/**
 * Randomly shuffle teams (Fisher-Yates)
 */
export function seedRandom(teams: TeamType[]): TeamType[] {
  const shuffled = [...teams];
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }
  return shuffled;
}

/**
 * Apply seeding method to teams
 */
export function applySeedingMethod(teams: TeamType[], method: SeedingMethod): TeamType[] {
  switch (method) {
    case 'mmr_total':
      return seedByMMR(teams);
    case 'captain_mmr':
      return seedByCaptainMMR(teams);
    case 'random':
      return seedRandom(teams);
    case 'manual':
      return teams; // Keep original order
    default:
      return teams;
  }
}

/**
 * Standard bracket seeding pattern for first round.
 * For 8 teams: 1v8, 4v5, 2v7, 3v6
 * This ensures highest seeds don't meet until later rounds.
 */
export function getFirstRoundPairings(seededTeams: TeamType[]): [TeamType | undefined, TeamType | undefined][] {
  const n = seededTeams.length;
  const bracketSize = Math.pow(2, Math.ceil(Math.log2(n)));
  const pairings: [TeamType | undefined, TeamType | undefined][] = [];

  // Generate standard bracket positions
  const positions = generateBracketPositions(bracketSize);

  for (let i = 0; i < bracketSize / 2; i++) {
    const pos1 = positions[i * 2];
    const pos2 = positions[i * 2 + 1];
    pairings.push([
      seededTeams[pos1 - 1], // Seeds are 1-indexed
      seededTeams[pos2 - 1],
    ]);
  }

  return pairings;
}

/**
 * Generate standard bracket positions for a power-of-2 bracket size.
 * Returns array of seed numbers in bracket order.
 */
function generateBracketPositions(size: number): number[] {
  if (size === 2) return [1, 2];

  const half = generateBracketPositions(size / 2);
  const result: number[] = [];

  for (const seed of half) {
    result.push(seed);
    result.push(size + 1 - seed);
  }

  return result;
}

/**
 * Apply seeded teams to first round matches
 */
export function applyTeamsToFirstRound(
  matches: BracketMatch[],
  seededTeams: TeamType[]
): BracketMatch[] {
  const pairings = getFirstRoundPairings(seededTeams);

  return matches.map((match) => {
    if (match.bracketType === 'winners' && match.round === 1) {
      const pairing = pairings[match.position];
      if (pairing) {
        return {
          ...match,
          radiantTeam: pairing[0],
          direTeam: pairing[1],
        };
      }
    }
    return match;
  });
}
