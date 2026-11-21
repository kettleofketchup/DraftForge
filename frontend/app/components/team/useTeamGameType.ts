import { toGameType, type GameTypeValue } from '~/components/game/constants';
import { useUserStore } from '~/store/userStore';

export function useTeamGameType(
  tournamentPk: number | null | undefined,
): GameTypeValue | undefined {
  const pk = useUserStore((s) => s.tournament?.pk);
  const game = useUserStore((s) => s.tournament?.game_type);
  if (tournamentPk == null || pk !== tournamentPk) return undefined;
  return toGameType(game);
}
