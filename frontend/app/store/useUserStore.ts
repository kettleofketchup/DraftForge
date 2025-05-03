import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { GuildMember, UserType, GuildMembers } from '~/components/user/types';
import { User } from '~/components/user/user';
import { UsersPage } from '~/pages/users/users';
import { get_dtx_members } from "~/components/api/api";
import { useCallback } from 'react';

interface UserState {
    user: UserType;

    setUser: (user: UserType) => void;
    clearUser: () => void;
    isStaff: () => boolean;
    discordUser: GuildMember;
    setDiscordUser: (discordUser:GuildMember)  => void;
    discordUsers: GuildMembers;
    setDiscordUsers: (users:GuildMembers)  => void;
    users: UserType[] ;
    setUsers: (uses: UserType[]) => void;
    addUser: (user: UserType) => void;
    clearUsers: () => void;

}
export const useUserStore = create<UserState>()(
    persist(
        (set, get) => ({
            user: new User({} as UserType),
            discordUser: {} as GuildMember,
            setDiscordUser: (discordUser) =>set({ discordUser }),
            discordUsers: [] as GuildMembers,
            setDiscordUsers: (discordUsers: GuildMembers) => set({ discordUsers }),
            setUser: (user) => set({ user }),
            clearUser: () => set({ user: {} as UserType }),
            isStaff: () => !!get().user?.is_staff,
            users: [] as UserType[],
            addUser: (user) => set({users: [...get().users, user]}),
            setUsers: (users) => set({ users }),
            clearUsers: () => set({ users: [] as UserType[] }),

        }),
        {
            name: 'dtx-user-storage', // key in localStorage
            partialize: (state) => ({ user: state.user }), // optionally limit what's stored
        }
    )
);
