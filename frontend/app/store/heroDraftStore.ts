// frontend/app/store/heroDraftStore.ts
import { create } from 'zustand';
import type { HeroDraft, HeroDraftTick, DraftTeam } from '~/components/herodraft/types';

interface HeroDraftState {
  draft: HeroDraft | null;
  tick: HeroDraftTick | null;
  selectedHeroId: number | null;
  searchQuery: string;

  // Actions
  setDraft: (draft: HeroDraft) => void;
  setTick: (tick: HeroDraftTick) => void;
  setSelectedHeroId: (heroId: number | null) => void;
  setSearchQuery: (query: string) => void;
  reset: () => void;

  // Computed helpers
  getCurrentTeam: () => DraftTeam | null;
  getOtherTeam: () => DraftTeam | null;
  isMyTurn: (userId: number) => boolean;
  getUsedHeroIds: () => number[];
}

export const useHeroDraftStore = create<HeroDraftState>((set, get) => ({
  draft: null,
  tick: null,
  selectedHeroId: null,
  searchQuery: '',

  setDraft: (draft) => set({ draft }),
  setTick: (tick) => set({ tick }),
  setSelectedHeroId: (heroId) => set({ selectedHeroId: heroId }),
  setSearchQuery: (query) => set({ searchQuery: query }),
  reset: () => set({ draft: null, tick: null, selectedHeroId: null, searchQuery: '' }),

  getCurrentTeam: () => {
    const { draft, tick } = get();
    if (!draft || !tick) return null;
    return draft.draft_teams.find((t) => t.id === tick.active_team_id) || null;
  },

  getOtherTeam: () => {
    const { draft, tick } = get();
    if (!draft || !tick) return null;
    return draft.draft_teams.find((t) => t.id !== tick.active_team_id) || null;
  },

  isMyTurn: (userId: number) => {
    const currentTeam = get().getCurrentTeam();
    return currentTeam?.captain?.pk === userId;
  },

  getUsedHeroIds: () => {
    const { draft } = get();
    if (!draft) return [];
    return draft.rounds
      .filter((r) => r.hero_id !== null)
      .map((r) => r.hero_id as number);
  },
}));
