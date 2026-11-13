import type { GameLobby } from './schemas';

/**
 * The bracket slot ('radiant' or 'dire' slot of the Game, not the in-game
 * side) of the team the lobby reported as the provisional winner.
 */
export function provisionalWinnerSlot(
  lobby: Pick<GameLobby, 'provisional_winner_team_id' | 'provisional_scored'> | null | undefined,
  slotRadiantTeamId: number | null | undefined,
  slotDireTeamId: number | null | undefined,
): 'radiant' | 'dire' | null {
  const winner = lobby?.provisional_winner_team_id;
  if (!lobby || winner == null || lobby.provisional_scored === false) return null;
  if (winner === slotRadiantTeamId) return 'radiant';
  if (winner === slotDireTeamId) return 'dire';
  return null;
}
