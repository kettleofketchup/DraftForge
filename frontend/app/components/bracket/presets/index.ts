export * from './types';
export { FOUR_TEAM_DOUBLE_ELIM } from './fourTeamDoubleElim';

import type { BracketPreset } from './types';
import { FOUR_TEAM_DOUBLE_ELIM } from './fourTeamDoubleElim';

/**
 * Get bracket preset by team count and format
 */
export function getPreset(teamCount: number, format: 'double_elimination' | 'swiss'): BracketPreset | undefined {
  if (format === 'double_elimination') {
    switch (teamCount) {
      case 4:
        return FOUR_TEAM_DOUBLE_ELIM;
      // Add more presets as needed: 8, 16, 32 teams
      default:
        return undefined;
    }
  }
  // Swiss presets can be added here
  return undefined;
}

/**
 * All available presets
 */
export const ALL_PRESETS: BracketPreset[] = [
  FOUR_TEAM_DOUBLE_ELIM,
];
