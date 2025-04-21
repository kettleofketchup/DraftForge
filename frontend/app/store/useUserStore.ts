// src/store/useUserStore.ts
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { User } from '../components/user/types';

interface UserState {
    user: User | null;
    setUser: (user: User) => void;
    clearUser: () => void;
    isStaff: () => boolean;
    users: User[] | null
    setUsers: (uses: User[]) => void;
    clearUsers: () => void;

}

export const useUserStore = create<UserState>()(
    persist(
        (set, get) => ({
            user: null,
            setUser: (user) => set({ user }),
            clearUser: () => set({ user: null }),
            isStaff: () => !!get().user?.is_staff,
            users: null,
            setUsers: (users) => set({ users }),
            clearUsers: () => set({ users: null }),

        }),
        {
            name: 'dtx-user-storage', // key in localStorage
            partialize: (state) => ({ user: state.user }), // optionally limit what's stored
        }
    )
);
