import {
  type QueryClient,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';
import { useEffect, useRef } from 'react';
import { toast } from 'sonner';
import {
  advanceWinner as advanceWinnerAPI,
  loadBracket as loadBracketAPI,
  saveBracket as saveBracketAPI,
} from '~/components/api/bracketAPI';
import type {
  BracketMatchDTO,
  BracketResponseDTO,
} from '~/components/bracket/schemas';
import type { BracketMatch } from '~/components/bracket/types';
import { parseBracketError } from '~/lib/bracketError';
import { getLogger } from '~/lib/logger';
import { mapApiMatchToMatch, useBracketStore } from '~/store/bracketStore';

const log = getLogger('bracket:save');

function storeFromResponse(data: BracketResponseDTO) {
  const apiMatches = data.matches as unknown as BracketMatchDTO[];
  return {
    matches: apiMatches.map((m) => mapApiMatchToMatch(m, apiMatches)),
    baseVersion: data.version ?? null,
    isDirty: false,
    hasStructuralEdits: false,
  };
}

/** Discards local bracket edits and loads the server's current bracket. */
export async function reloadBracket(
  queryClient: QueryClient,
  tournamentId: number,
): Promise<void> {
  const data = await queryClient.fetchQuery({
    queryKey: ['bracket', tournamentId],
    queryFn: () => loadBracketAPI(tournamentId),
    staleTime: 0,
  });
  useBracketStore.setState({
    ...storeFromResponse(data),
    isVirtual: data.matches.length === 0,
  });
  log.info('bracket_reloaded', { tournamentId });
}

/**
 * Settles one advance-winner write. Once none are left in flight and there
 * are no structural edits, the bracket is refetched before the store is
 * marked clean, so a refetch never lands on top of a newer local result.
 */
async function settleResultWrite(
  queryClient: QueryClient,
  tournamentId: number | undefined,
): Promise<boolean> {
  if (useBracketStore.getState().endResultWrite() > 0) return false;
  await queryClient.invalidateQueries({ queryKey: ['bracket', tournamentId] });
  const { pendingResultWrites, hasStructuralEdits } =
    useBracketStore.getState();
  return pendingResultWrites === 0 && !hasStructuralEdits;
}

/**
 * Fetches bracket data via TanStack Query and seeds the Zustand bracketStore.
 * Polling pauses automatically when the bracket has unsaved edits (isDirty).
 */
export function useBracketQuery(tournamentId: number | null) {
  const isDirty = useBracketStore((state) => state.isDirty);
  const previousDataRef = useRef<string | null>(null);

  const query = useQuery({
    queryKey: ['bracket', tournamentId],
    queryFn: () => loadBracketAPI(tournamentId!),
    enabled: !!tournamentId,
    staleTime: 0, // Override global 5min default so invalidateQueries() triggers immediate refetch
    refetchInterval: isDirty ? false : 5_000,
  });

  // Seed Zustand store from query data
  useEffect(() => {
    if (!query.data || isDirty) return;
    useBracketStore.setState({
      baseVersion: query.data.version ?? null,
      hasStructuralEdits: false,
    });

    // NOTE: BracketResponse.matches is typed as BracketMatch[] but at runtime
    // is actually BracketMatchDTO[] (snake_case) due to Zod schema parsing.
    // This cast is a workaround for a pre-existing type mismatch in bracketAPI.tsx.
    const apiMatches = query.data.matches as unknown as BracketMatchDTO[];

    // Handle empty bracket — use getState() to avoid subscribing to matches
    if (apiMatches.length === 0) {
      if (useBracketStore.getState().matches.length > 0) {
        useBracketStore.setState({
          matches: [],
          nodes: [],
          edges: [],
          isDirty: false,
          isVirtual: true,
        });
        log.debug('Bracket cleared (no matches from backend)');
      }
      previousDataRef.current = null;
      return;
    }

    // Map API matches to frontend format
    const mappedMatches = apiMatches.map((m) =>
      mapApiMatchToMatch(m, apiMatches),
    );

    // Compare to avoid unnecessary rerenders
    const newKey = JSON.stringify(mappedMatches);

    if (newKey === previousDataRef.current) return;
    previousDataRef.current = newKey;

    useBracketStore.setState({
      matches: mappedMatches,
      isDirty: false,
      isVirtual: false,
    });
    log.debug('Bracket updated from query', {
      matchCount: mappedMatches.length,
    });
  }, [query.data, isDirty]);

  return query;
}

interface MatchResultVars {
  gameId: number;
  winner: 'radiant' | 'dire' | null;
}

/**
 * Persists a single match result via advance_winner (issue #466). The caller
 * applies the change to the store first. Writes may overlap (issue #963): the
 * store stays dirty until the last one settles, then takes the server bracket.
 */
export function usePersistMatchResult(tournamentId: number | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ gameId, winner }: MatchResultVars) =>
      advanceWinnerAPI(gameId, winner),
    onMutate: () => {
      useBracketStore.getState().beginResultWrite();
    },
    onSuccess: async (_data, { gameId, winner }) => {
      log.info('bracket_match_result_saved', { tournamentId, gameId, winner });
      if (await settleResultWrite(queryClient, tournamentId)) {
        useBracketStore.setState({ isDirty: false });
      }
    },
    onError: async (error, { gameId, winner }) => {
      const { message, code, details } = parseBracketError(error);
      log.error('bracket_match_result_failed', {
        tournamentId,
        gameId,
        winner,
        message,
        code,
        details,
      });
      toast.error(`Failed to save match result: ${message}`);
      if (!(await settleResultWrite(queryClient, tournamentId))) return;
      const cached = queryClient.getQueryData<BracketResponseDTO>([
        'bracket',
        tournamentId,
      ]);
      if (cached) {
        useBracketStore.setState(storeFromResponse(cached));
      } else {
        useBracketStore.setState({ isDirty: false });
      }
    },
  });
}

/**
 * Mutation for saving bracket. Invalidates the bracket query cache on success.
 */
export function useSaveBracket(tournamentId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (matches: BracketMatch[]) =>
      saveBracketAPI(
        tournamentId,
        matches,
        useBracketStore.getState().baseVersion,
      ),
    onSuccess: (data) => {
      // Update Zustand store with saved matches (they now have backend PKs)
      const saved = storeFromResponse(data);
      const savedMatches = saved.matches;
      useBracketStore.setState({ ...saved, isVirtual: false });
      // Invalidate to ensure cache is fresh
      queryClient.invalidateQueries({ queryKey: ['bracket', tournamentId] });
      log.info('bracket_saved', {
        tournamentId,
        matchCount: savedMatches.length,
      });
      toast.success('Bracket saved');
    },
    onError: (error) => {
      const { message, code, details } = parseBracketError(error);
      log.error('bracket_save_failed', {
        tournamentId,
        message,
        code,
        details,
      });
      if (code === 'bracket_stale') {
        toast.error(message, {
          id: `bracket-stale-${tournamentId}`,
          duration: Infinity,
          description: 'Your unsaved edits are kept until you reload.',
          action: {
            label: 'Reload bracket',
            onClick: () => {
              reloadBracket(queryClient, tournamentId).catch((err: unknown) => {
                log.error('bracket_reload_failed', {
                  tournamentId,
                  ...parseBracketError(err),
                });
                toast.error('Failed to reload the bracket');
              });
            },
          },
        });
        return;
      }
      toast.error(`Failed to save bracket: ${message}`);
    },
  });
}
