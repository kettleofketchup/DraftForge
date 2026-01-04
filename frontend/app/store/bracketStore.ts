import { create } from 'zustand';
import type { Node, Edge } from '@xyflow/react';
import type { BracketMatch, SeedingMethod } from '~/components/bracket/types';
import type { TeamType } from '~/components/tournament/types.d';
import { generateBracket, reseedBracket } from '~/components/bracket/utils/bracketFactory';
import { api } from '~/components/api/axios';
import { BracketResponseSchema, type BracketMatch as ApiBracketMatch } from '~/components/bracket/schemas';
import { getLogger } from '~/lib/logger';

const log = getLogger('bracketStore');

/**
 * Converts API response match (snake_case) to frontend match (camelCase)
 */
function mapApiMatchToMatch(apiMatch: ApiBracketMatch): BracketMatch {
  return {
    id: apiMatch.id,
    gameId: apiMatch.pk,
    round: apiMatch.round,
    position: apiMatch.position,
    bracketType: apiMatch.bracket_type,
    radiantTeam: apiMatch.radiant_team,
    direTeam: apiMatch.dire_team,
    winner: apiMatch.winning_team ? 'radiant' : undefined, // simplified - actual logic may vary
    status: apiMatch.status,
    steamMatchId: apiMatch.gameid,
    nextMatchId: apiMatch.next_game?.toString(),
    nextMatchSlot: apiMatch.next_game_slot,
  };
}

interface BracketStore {
  // State
  matches: BracketMatch[];
  nodes: Node[];
  edges: Edge[];
  isDirty: boolean;
  isVirtual: boolean;
  isLoading: boolean;
  pollInterval: ReturnType<typeof setInterval> | null;

  // Actions
  setMatches: (matches: BracketMatch[]) => void;
  setNodes: (nodes: Node[]) => void;
  setEdges: (edges: Edge[]) => void;

  // Bracket operations
  generateBracket: (teams: TeamType[], method: SeedingMethod) => void;
  reseedBracket: (teams: TeamType[], method: SeedingMethod) => void;
  assignTeamToSlot: (matchId: string, slot: 'radiant' | 'dire', team: TeamType) => void;
  removeTeamFromSlot: (matchId: string, slot: 'radiant' | 'dire') => void;
  setMatchWinner: (matchId: string, winner: 'radiant' | 'dire') => void;
  advanceWinner: (matchId: string) => void;

  // Persistence
  saveBracket: (tournamentId: number) => Promise<void>;
  loadBracket: (tournamentId: number) => Promise<void>;
  resetBracket: () => void;

  // Polling
  startPolling: (tournamentId: number, intervalMs?: number) => void;
  stopPolling: () => void;
}

export const useBracketStore = create<BracketStore>()((set, get) => ({
  matches: [],
  nodes: [],
  edges: [],
  isDirty: false,
  isVirtual: true,
  isLoading: false,
  pollInterval: null,

  setMatches: (matches) => set({ matches, isDirty: true }),
  setNodes: (nodes) => set({ nodes }),
  setEdges: (edges) => set({ edges }),

  generateBracket: (teams, method) => {
    log.debug('Generating bracket', { teams: teams.length, method });
    const result = generateBracket('double_elimination', teams, method);
    set({
      matches: result.matches,
      isDirty: true,
      isVirtual: true,
    });
  },

  reseedBracket: (teams, method) => {
    log.debug('Reseeding bracket', { method });
    const reseeded = reseedBracket(get().matches, teams, method);
    set({
      matches: reseeded,
      isDirty: true,
    });
  },

  assignTeamToSlot: (matchId, slot, team) => {
    log.debug('Assigning team to slot', { matchId, slot, team: team.name });
    set((state) => ({
      matches: state.matches.map((m) =>
        m.id === matchId
          ? { ...m, [slot === 'radiant' ? 'radiantTeam' : 'direTeam']: team }
          : m
      ),
      isDirty: true,
    }));
  },

  removeTeamFromSlot: (matchId, slot) => {
    log.debug('Removing team from slot', { matchId, slot });
    set((state) => ({
      matches: state.matches.map((m) =>
        m.id === matchId
          ? { ...m, [slot === 'radiant' ? 'radiantTeam' : 'direTeam']: undefined }
          : m
      ),
      isDirty: true,
    }));
  },

  setMatchWinner: (matchId, winner) => {
    log.debug('Setting match winner', { matchId, winner });
    set((state) => ({
      matches: state.matches.map((m) =>
        m.id === matchId ? { ...m, winner, status: 'completed' as const } : m
      ),
      isDirty: true,
    }));
  },

  advanceWinner: (matchId) => {
    const match = get().matches.find((m) => m.id === matchId);
    if (!match?.winner || !match.nextMatchId) return;

    const winningTeam =
      match.winner === 'radiant' ? match.radiantTeam : match.direTeam;
    if (!winningTeam) return;

    log.debug('Advancing winner', { matchId, nextMatchId: match.nextMatchId });
    get().assignTeamToSlot(match.nextMatchId, match.nextMatchSlot!, winningTeam);
  },

  saveBracket: async (tournamentId) => {
    log.debug('Saving bracket', { tournamentId });
    set({ isLoading: true });
    try {
      await api.post(`/bracket/tournaments/${tournamentId}/save/`, {
        matches: get().matches,
      });
      set({ isDirty: false, isVirtual: false });
      log.debug('Bracket saved successfully');
    } catch (error) {
      log.error('Failed to save bracket', error);
      throw error;
    } finally {
      set({ isLoading: false });
    }
  },

  loadBracket: async (tournamentId) => {
    log.debug('Loading bracket', { tournamentId });
    set({ isLoading: true });
    try {
      const response = await api.get(`/bracket/tournaments/${tournamentId}/`);
      const data = BracketResponseSchema.parse(response.data);

      if (data.matches.length > 0) {
        const mappedMatches = data.matches.map(mapApiMatchToMatch);
        set({
          matches: mappedMatches,
          isDirty: false,
          isVirtual: false,
        });
        log.debug('Bracket loaded', { matchCount: mappedMatches.length });
      }
    } catch (error) {
      log.error('Failed to load bracket', error);
    } finally {
      set({ isLoading: false });
    }
  },

  resetBracket: () => {
    log.debug('Resetting bracket');
    set({
      matches: [],
      nodes: [],
      edges: [],
      isDirty: false,
      isVirtual: true,
    });
  },

  startPolling: (tournamentId, intervalMs = 5000) => {
    get().stopPolling();
    log.debug('Starting bracket polling', { tournamentId, intervalMs });

    const interval = setInterval(() => {
      // Only poll if not dirty (no unsaved changes)
      if (!get().isDirty) {
        get().loadBracket(tournamentId);
      }
    }, intervalMs);

    set({ pollInterval: interval });
  },

  stopPolling: () => {
    const interval = get().pollInterval;
    if (interval) {
      log.debug('Stopping bracket polling');
      clearInterval(interval);
      set({ pollInterval: null });
    }
  },
}));
