// src/store/useUserStore.ts
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { User } from '../components/user/types';
import { UsersPage } from '~/pages/users/users';

interface UserState {
    user: User;
    setUser: (user: User) => void;
    clearUser: () => void;
    isStaff: () => boolean;
    users: User[] ;
    setUsers: (uses: User[]) => void;
    addUser: (user: User) => void;
    clearUsers: () => void;

}

export const useUserStore = create<UserState>()(
    persist(
        (set, get) => ({
            user: {} as User,
            setUser: (user) => set({ user }),
            clearUser: () => set({ user: {} as User }),
            isStaff: () => !!get().user?.is_staff,
            users: [] as User[],
            addUser: (user) => set({users: [...get().users, user]}),
            setUsers: (users) => set({ users }),
            clearUsers: () => set({ users: [] as User[] }),

        }),
        {
            name: 'dtx-user-storage', // key in localStorage
            partialize: (state) => ({ user: state.user }), // optionally limit what's stored
        }
    )
);
