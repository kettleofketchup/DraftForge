import { useQuery } from '@tanstack/react-query';
import { useUserStore } from '~/store/userStore';
import { getTournamentViewer } from './api';
import { tournamentViewerKeys } from './queryKeys';

/** Server-side can_edit_tournament for the current user; false until it loads. */
export function useCanEditTournamentFromServer(
  tournamentPk: number | null | undefined,
): boolean {
  const viewerPk = useUserStore((state) => state.currentUser?.pk ?? null);
  const { data } = useQuery({
    queryKey: tournamentViewerKeys.detail(tournamentPk ?? -1, viewerPk),
    queryFn: () => getTournamentViewer(tournamentPk!),
    enabled: !!tournamentPk && viewerPk !== null,
  });
  return data?.can_edit_tournament === true;
}
