import type { NavigationType } from 'react-router';

interface BracketMatchSelectionState {
  bracketMatchSelection: { tournamentId: number; matchId: string };
}

export function bracketMatchSelectionState(
  tournamentId: number,
  matchId: string,
): BracketMatchSelectionState {
  return { bracketMatchSelection: { tournamentId, matchId } };
}

/** True for the URL update a bracket node click made after opening that match itself. */
export function isLocalBracketMatchSelection(
  navigationType: NavigationType,
  state: unknown,
  tournamentId: number | null,
  matchId: string | null,
): boolean {
  if (navigationType !== 'REPLACE' || tournamentId === null || !matchId) {
    return false;
  }
  const selection = (state as Partial<BracketMatchSelectionState> | null)
    ?.bracketMatchSelection;
  return (
    selection?.tournamentId === tournamentId && selection.matchId === matchId
  );
}
