import { create } from 'zustand';

export interface PageNavOption {
  value: string;
  label: string;
}

interface PageNavState {
  options: PageNavOption[] | null;
  value: string;
  onValueChange: ((value: string) => void) | null;
  setPageNav: (
    options: PageNavOption[],
    value: string,
    onValueChange: (v: string) => void,
  ) => void;
  clearPageNav: () => void;
  updateValue: (value: string) => void;
}

export const usePageNavStore = create<PageNavState>((set) => ({
  options: null,
  value: '',
  onValueChange: null,
  setPageNav: (options, value, onValueChange) =>
    set({ options, value, onValueChange }),
  clearPageNav: () => set({ options: null, value: '', onValueChange: null }),
  updateValue: (value) => set({ value }),
}));
