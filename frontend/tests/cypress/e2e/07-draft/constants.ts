/**
 * Constants for draft tests
 */

// Test tournament keys - these match the backend TEST_TOURNAMENTS config
export const TEST_TOURNAMENT_KEYS = {
  CAPTAIN_DRAFT: 'captain_draft_test',
  BRACKET_TEST: 'bracket_test',
} as const;

// Test user roles for draft testing
export const DRAFT_TEST_ROLES = {
  CAPTAIN_1: 'captain_1',
  CAPTAIN_2: 'captain_2',
  PLAYER: 'regular_player',
} as const;
