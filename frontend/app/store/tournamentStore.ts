import { create } from 'zustand';

interface TournamentState {
  live: boolean;
  setLive: (live: boolean) => void;
  activeTab: string;
  setActiveTab: (tab: string) => void;
  liveReload: boolean;
  setLiveReload: (liveReload: boolean) => void;
  toggleLiveReload: () => void;
}

export const useTournamentStore = create<TournamentState>((set, get) => ({
  live: false,
  setLive: (live) => set({ live }),
  activeTab: 'players',
  setActiveTab: (tab) => set({ activeTab: tab }),
  liveReload: false,
  toggleLiveReload: () => get().setLiveReload(!get().liveReload),
  setLiveReload: (liveReload) => set({ liveReload }),
}));
