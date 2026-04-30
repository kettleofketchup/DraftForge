import { useMutation, useQueryClient } from '@tanstack/react-query';

import { updateLeague } from '~/components/api/api';
import type { LeagueType } from '~/components/league/schemas';

/**
 * TanStack Query mutation for PATCH /api/leagues/<pk>/.
 *
 * On success: invalidates the ['leagues'] list query so list views refresh.
 *
 * NOTE: We intentionally do NOT call setQueryData(['league', pk], data) here.
 * The current `useLeague` hook (frontend/app/components/league/hooks/useLeague.ts)
 * uses raw `useState`/`useEffect` and `fetchLeague`, NOT TanStack Query, so
 * `setQueryData(['league', pk])` would write to a cache nobody reads. The
 * League detail page refresh happens via the modal's `onSuccess` callback,
 * which the parent route already wires to its own `refetch`.
 */
export function useUpdateLeagueMutation(leagueId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: Partial<LeagueType>) => updateLeague(leagueId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['leagues'] });
    },
  });
}
