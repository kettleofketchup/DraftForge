import { useEffect, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { loadBracket as loadBracketAPI, saveBracket as saveBracketAPI } from '~/components/api/bracketAPI';
import { useBracketStore, mapApiMatchToMatch } from '~/store/bracketStore';
import type { BracketMatch } from '~/components/bracket/types';
import type { BracketMatchDTO } from '~/components/bracket/schemas';
import { getLogger } from '~/lib/logger';

const log = getLogger('useBracket');

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

  // Seed Zustand store from query data (replaces bracketStore.loadBracket logic)
  useEffect(() => {
    if (!query.data || isDirty) return;

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
    const mappedMatches = apiMatches.map((m) => mapApiMatchToMatch(m, apiMatches));

    // Compare to avoid unnecessary rerenders (same logic as old bracketStore.loadBracket)
    const newKey = mappedMatches
      .map((m) => `${m.id}-${m.winner}-${m.status}-${m.radiantTeam?.pk}-${m.direTeam?.pk}`)
      .join('|');

    if (newKey === previousDataRef.current) return;
    previousDataRef.current = newKey;

    useBracketStore.setState({
      matches: mappedMatches,
      isDirty: false,
      isVirtual: false,
    });
    log.debug('Bracket updated from query', { matchCount: mappedMatches.length });
  }, [query.data, isDirty]);

  return query;
}

/**
 * Mutation for saving bracket. Invalidates the bracket query cache on success.
 */
export function useSaveBracket(tournamentId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (matches: BracketMatch[]) => saveBracketAPI(tournamentId, matches),
    onSuccess: (data) => {
      // Update Zustand store with saved matches (they now have backend PKs)
      const apiMatches = data.matches as unknown as BracketMatchDTO[];
      const savedMatches = apiMatches.map((m) => mapApiMatchToMatch(m, apiMatches));
      useBracketStore.setState({
        matches: savedMatches,
        isDirty: false,
        isVirtual: false,
      });
      // Invalidate to ensure cache is fresh
      queryClient.invalidateQueries({ queryKey: ['bracket', tournamentId] });
      log.debug('Bracket saved', { matchCount: savedMatches.length });
    },
    onError: (error) => {
      log.error('Failed to save bracket', error);
    },
  });
}
