import { create } from 'zustand';
import { getDraftStyleMMRs } from '~/components/api/api';
import type { DraftStyleMMRsAPIReturn } from '~/components/api/types';
export interface TournamentState {
  live: boolean;
  setLive: (live: boolean) => void;
  activeTab: string;
  setActiveTab: (tab: string) => void;
  livePolling: boolean;
  setLivePolling: (livePolling: boolean) => void;
  toggleLivePolling: () => void;
  autoAdvance: boolean;
  setAutoAdvance: (autoAdvance: boolean) => void;
  toggleAutoAdvance: () => void;
  draftPredictedMMRs: DraftStyleMMRsAPIReturn;
  setDraftPredictedMMRs: (data: DraftStyleMMRsAPIReturn) => void;
  updateDraftPredictedMMRs: (draft_pk: number) => Promise<void>;
}

export const useTournamentStore = create<TournamentState>((set, get) => ({
  live: false,
  setLive: (live: boolean) => set({ live }),
  activeTab: 'players',
  setActiveTab: (tab: string) => set({ activeTab: tab }),
  livePolling: true, // Default ON
  setLivePolling: (livePolling: boolean) => set({ livePolling }),
  toggleLivePolling: () => get().setLivePolling(!get().livePolling),
  autoAdvance: false, // Default OFF
  toggleAutoAdvance: () => get().setAutoAdvance(!get().autoAdvance),
  setAutoAdvance: (autoAdvance: boolean) => set({ autoAdvance }),
  draftPredictedMMRs: {} as DraftStyleMMRsAPIReturn,
  updateDraftPredictedMMRs: async (pk: number) => {
    try {
      const response = await getDraftStyleMMRs({ pk });
      set({ draftPredictedMMRs: response });
    } catch (error) {
      console.error('Failed to fetch draft predicted MMRs:', error);
    }
  },
  setDraftPredictedMMRs: (data: DraftStyleMMRsAPIReturn) =>
    set({ draftPredictedMMRs: data }),
}));
