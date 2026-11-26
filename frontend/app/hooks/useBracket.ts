import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
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
import {
  isBracketStoreFor,
  mapApiMatchToMatch,
  useBracketStore,
} from '~/store/bracketStore';

const log = getLogger('bracket:save');

/**
 * Fetches bracket data via TanStack Query and seeds the Zustand bracketStore.
 * Polling pauses automatically when the bracket has unsaved edits (isDirty).
 * While dirty, server data never replaces the edits; `serverChanged` says the
 * server bracket moved on since it was loaded.
 * Switching tournaments drops the previous tournament's bracket, edits included.
 */
export function useBracketQuery(tournamentId: number | null) {
  const isDirty = useBracketStore(
    (state) => state.isDirty && state.tournamentId === tournamentId,
  );
  const previousDataRef = useRef<string | null>(null);
  const [serverChanged, setServerChanged] = useState(false);

  useLayoutEffect(() => {
    if (useBracketStore.getState().tournamentId === tournamentId) return;
    previousDataRef.current = null;
    useBracketStore.getState().bindTournament(tournamentId);
  }, [tournamentId]);

  const query = useQuery({
    queryKey: ['bracket', tournamentId],
    queryFn: () => loadBracketAPI(tournamentId!),
    enabled: !!tournamentId,
    staleTime: 0, // Override global 5min default so invalidateQueries() triggers immediate refetch
    refetchInterval: isDirty ? false : 5_000,
  });

  useEffect(() => {
    if (!query.data) return;

    // NOTE: BracketResponse.matches is typed as BracketMatch[] but at runtime
    // is actually BracketMatchDTO[] (snake_case) due to Zod schema parsing.
    // This cast is a workaround for a pre-existing type mismatch in bracketAPI.tsx.
    const apiMatches = query.data.matches as unknown as BracketMatchDTO[];

    if (isDirty) {
      const serverKey = apiMatches.length
        ? JSON.stringify(
            apiMatches.map((m) => mapApiMatchToMatch(m, apiMatches)),
          )
        : null;
      const localKey = JSON.stringify(useBracketStore.getState().matches);
      setServerChanged(
        serverKey !== previousDataRef.current && serverKey !== localKey,
      );
      return;
    }
    setServerChanged(false);

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

  return { ...query, serverChanged };
}

interface MatchResultVars {
  gameId: number;
  winner: 'radiant' | 'dire' | null;
}

/**
 * Persists a single match result via advance_winner (issue #466). The caller
 * applies the change to the store first; on success the server's bracket
 * replaces it, on failure the last fetched bracket is restored.
 */
export function usePersistMatchResult(tournamentId: number | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ gameId, winner }: MatchResultVars) =>
      advanceWinnerAPI(gameId, winner),
    onSuccess: (_data, { gameId, winner }) => {
      if (isBracketStoreFor(tournamentId)) {
        useBracketStore.setState({ isDirty: false });
      }
      queryClient.invalidateQueries({ queryKey: ['bracket', tournamentId] });
      log.info('bracket_match_result_saved', { tournamentId, gameId, winner });
    },
    onError: (error, { gameId, winner }) => {
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
      const cached = queryClient.getQueryData<BracketResponseDTO>([
        'bracket',
        tournamentId,
      ]);
      if (cached && isBracketStoreFor(tournamentId)) {
        const apiMatches = cached.matches as unknown as BracketMatchDTO[];
        useBracketStore.setState({
          matches: apiMatches.map((m) => mapApiMatchToMatch(m, apiMatches)),
          isDirty: false,
        });
      }
      queryClient.invalidateQueries({ queryKey: ['bracket', tournamentId] });
    },
  });
}

/**
 * Mutation for saving bracket. Invalidates the bracket query cache on success.
 */
export function useSaveBracket(tournamentId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (matches: BracketMatch[]) => {
      if (!isBracketStoreFor(tournamentId)) {
        throw new Error('This bracket belongs to another tournament');
      }
      return saveBracketAPI(tournamentId, matches);
    },
    onSuccess: (data) => {
      if (!isBracketStoreFor(tournamentId)) {
        queryClient.invalidateQueries({ queryKey: ['bracket', tournamentId] });
        log.info('bracket_saved_after_switch', { tournamentId });
        toast.success('Bracket saved');
        return;
      }
      // Update Zustand store with saved matches (they now have backend PKs)
      const apiMatches = data.matches as unknown as BracketMatchDTO[];
      const savedMatches = apiMatches.map((m) =>
        mapApiMatchToMatch(m, apiMatches),
      );
      useBracketStore.setState({
        matches: savedMatches,
        isDirty: false,
        isVirtual: false,
      });
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
      toast.error(`Failed to save bracket: ${message}`);
    },
  });
}
