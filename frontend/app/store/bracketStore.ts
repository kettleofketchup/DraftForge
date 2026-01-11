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
 * Generate a consistent string ID for bracket matches
 * Format: {bracketType}-{round}-{position} e.g., "winners-1-0"
 */
function generateMatchId(bracketType: string, round: number, position: number): string {
  // Use short prefixes for cleaner IDs
  const typePrefix: Record<string, string> = {
    winners: 'w',
    losers: 'l',
    grand_finals: 'gf',
    swiss: 'sw',
  };

  return `${typePrefix[bracketType] || bracketType}-${round}-${position}`;
}

/**
 * Converts API response match (snake_case) to frontend match (camelCase)
 */
function mapApiMatchToMatch(apiMatch: ApiBracketMatch, allMatches: ApiBracketMatch[]): BracketMatch {
  // Generate consistent string ID from bracket structure
  const id = generateMatchId(apiMatch.bracket_type, apiMatch.round, apiMatch.position);

  // Determine winner by comparing winning_team with radiant/dire teams
  let winner: 'radiant' | 'dire' | undefined;
  if (apiMatch.winning_team && apiMatch.radiant_team && apiMatch.dire_team) {
    if (apiMatch.winning_team.pk === apiMatch.radiant_team.pk) {
      winner = 'radiant';
    } else if (apiMatch.winning_team.pk === apiMatch.dire_team.pk) {
      winner = 'dire';
    }
  }

  // Find the next match by pk and generate its string ID
  let nextMatchId: string | undefined;
  if (apiMatch.next_game) {
    const nextMatch = allMatches.find(m => m.pk === apiMatch.next_game);
    if (nextMatch) {
      nextMatchId = generateMatchId(nextMatch.bracket_type, nextMatch.round, nextMatch.position);
    }
  }

  // Find the loser's next match
  let loserNextMatchId: string | undefined;
  if (apiMatch.loser_next_game) {
    const loserNextMatch = allMatches.find(m => m.pk === apiMatch.loser_next_game);
    if (loserNextMatch) {
      loserNextMatchId = generateMatchId(loserNextMatch.bracket_type, loserNextMatch.round, loserNextMatch.position);
    }
  }

  return {
    id,
    gameId: apiMatch.pk,
    round: apiMatch.round,
    position: apiMatch.position,
    bracketType: apiMatch.bracket_type,
    eliminationType: apiMatch.elimination_type || 'double',
    radiantTeam: apiMatch.radiant_team,
    direTeam: apiMatch.dire_team,
    winner,
    status: apiMatch.status,
    steamMatchId: apiMatch.gameid,
    nextMatchId,
    nextMatchSlot: apiMatch.next_game_slot,
    loserNextMatchId,
    loserNextMatchSlot: apiMatch.loser_next_game_slot,
    swissRecordWins: apiMatch.swiss_record_wins,
    swissRecordLosses: apiMatch.swiss_record_losses,
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
    if (!match?.winner) return;

    const winningTeam =
      match.winner === 'radiant' ? match.radiantTeam : match.direTeam;
    const losingTeam =
      match.winner === 'radiant' ? match.direTeam : match.radiantTeam;

    // Advance winner to next match
    if (winningTeam && match.nextMatchId && match.nextMatchSlot) {
      log.debug('Advancing winner', { matchId, nextMatchId: match.nextMatchId });
      get().assignTeamToSlot(match.nextMatchId, match.nextMatchSlot, winningTeam);
    }

    // Advance loser to losers bracket (double elimination)
    if (losingTeam && match.loserNextMatchId && match.loserNextMatchSlot) {
      log.debug('Advancing loser to losers bracket', {
        matchId,
        loserNextMatchId: match.loserNextMatchId,
      });
      get().assignTeamToSlot(match.loserNextMatchId, match.loserNextMatchSlot, losingTeam);
    }
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
        // Pass all matches to mapper so it can resolve next_game references
        const mappedMatches = data.matches.map(m => mapApiMatchToMatch(m, data.matches));
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
