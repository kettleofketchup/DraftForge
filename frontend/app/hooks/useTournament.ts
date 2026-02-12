import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchTournament, getTournaments, updateTournament } from '~/components/api/api';
import type { TournamentType, TournamentsType } from '~/components/tournament/types';

export function useTournament(pk: number | null) {
  return useQuery({
    queryKey: ['tournament', pk],
    queryFn: () => fetchTournament(pk!),
    enabled: !!pk,
    refetchInterval: 10_000,
  });
}

export function useTournaments(filters?: { organizationId?: number; leagueId?: number }) {
  return useQuery({
    queryKey: ['tournaments', filters],
    queryFn: () => getTournaments(filters),
  });
}

export function useUpdateTournament(pk: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: Partial<TournamentType>) => updateTournament(pk, data),
    onSuccess: (updated) => {
      queryClient.setQueryData(['tournament', pk], updated);
    },
  });
}
