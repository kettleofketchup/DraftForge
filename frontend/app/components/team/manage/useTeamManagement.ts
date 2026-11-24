import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from '@tanstack/react-query';
import { useEffect, useRef } from 'react';
import { setTeamPlacement } from '~/components/api/bracketAPI';
import {
  fetchManagedTeam,
  fetchTeamHistory,
  runTeamAction,
  type ManagedTeam,
  type TeamAction,
  type TeamActionBody,
  type TeamHistoryPage,
} from '~/components/api/teamManagementAPI';
import { useCanManageCurrentTournament } from '~/hooks/useCanManageTournament';
import { getLogger } from '~/lib/logger';

const log = getLogger('teamManage');

const HISTORY_PAGE_SIZE = 25;

export const teamManageKeys = {
  all: (teamId: number) => ['team', teamId] as const,
  managed: (teamId: number) => ['team', teamId, 'managed'] as const,
  history: (teamId: number, page?: number) =>
    page === undefined
      ? (['team', teamId, 'history'] as const)
      : (['team', teamId, 'history', page] as const),
};

export function useManagedTeam(
  teamId: number | null | undefined,
  opts: { enabled: boolean },
): UseQueryResult<ManagedTeam> {
  return useQuery({
    queryKey: teamManageKeys.managed(teamId ?? -1),
    queryFn: () => fetchManagedTeam(teamId!),
    enabled: opts.enabled && teamId != null,
  });
}

export function useTeamHistory(
  teamId: number,
  page: number,
  opts: { enabled?: boolean } = {},
): UseQueryResult<TeamHistoryPage> {
  return useQuery({
    queryKey: teamManageKeys.history(teamId, page),
    queryFn: () => fetchTeamHistory(teamId, page, HISTORY_PAGE_SIZE),
    // Keep the last page only while paging the same team.
    placeholderData: (previous, previousQuery) =>
      previousQuery?.queryKey[1] === teamId ? previous : undefined,
    enabled: opts.enabled ?? true,
  });
}

export type TeamActionVariables = { action: TeamAction; body: TeamActionBody };

// No onError: useOverrideRetry owns every rejection (409s, reason errors).
export function useTeamActionMutation(
  teamId: number,
  tournamentPk: number | undefined,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ action, body }: TeamActionVariables) =>
      runTeamAction(teamId, action, body),
    onSuccess: (team, { action }) => {
      queryClient.setQueryData(teamManageKeys.managed(teamId), { ...team });
      if (tournamentPk != null) {
        queryClient.invalidateQueries({
          queryKey: ['tournament', tournamentPk],
        });
      }
      queryClient.invalidateQueries({
        queryKey: teamManageKeys.history(teamId),
      });
      log.info('Team action succeeded', { teamId, kind: action.kind });
    },
  });
}

/** Bracket placement (null = back in the tournament); not a team log action. */
export function useSetTeamPlacement(teamId: number, tournamentId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      placement,
      reason,
    }: {
      placement: number | null;
      reason: string;
    }) => setTeamPlacement(tournamentId, teamId, placement, reason),
    onSuccess: ({ placement }) => {
      queryClient.invalidateQueries({ queryKey: ['tournament', tournamentId] });
      queryClient.invalidateQueries({
        queryKey: teamManageKeys.managed(teamId),
      });
      queryClient.invalidateQueries({
        queryKey: teamManageKeys.history(teamId),
      });
      log.info('Team placement set', { teamId, placement });
    },
  });
}

/** Display-only mirror of can_edit_tournament for the store tournament. */
export function useCanEditCurrentTournament(): boolean {
  return useCanManageCurrentTournament();
}

type PkLike = { pk?: number | null } | number | null | undefined;

export type RosterLike = {
  captain?: PkLike;
  deputy_captain?: PkLike;
  members?: PkLike[] | null;
  dropin_members?: PkLike[] | null;
  left_members?: PkLike[] | null;
};

const pkOf = (user: PkLike): number | null =>
  typeof user === 'number' ? user : (user?.pk ?? null);

const sortedPks = (users: PkLike[] | null | undefined): number[] =>
  (users ?? [])
    .map(pkOf)
    .filter((pk): pk is number => pk != null)
    .sort((a, b) => a - b);

export function rosterSignature(team: RosterLike): string {
  return JSON.stringify([
    pkOf(team.captain),
    pkOf(team.deputy_captain),
    sortedPks(team.members),
    sortedPks(team.dropin_members),
    sortedPks(team.left_members),
  ]);
}

/** Refetch an open team's queries when the live store roster changes. */
export function useInvalidateOnRosterChange(
  teamId: number | null | undefined,
  signature: string,
): void {
  const queryClient = useQueryClient();
  const seen = useRef<{ teamId: number; signature: string } | null>(null);

  useEffect(() => {
    if (teamId == null) {
      seen.current = null;
      return;
    }
    const previous = seen.current;
    seen.current = { teamId, signature };
    if (
      previous &&
      previous.teamId === teamId &&
      previous.signature !== signature
    ) {
      queryClient.invalidateQueries({ queryKey: teamManageKeys.all(teamId) });
    }
  }, [teamId, signature, queryClient]);
}
