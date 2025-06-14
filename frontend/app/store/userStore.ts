import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type {
  GuildMember,
  UserType,
  GuildMembers,
  UsersType,
} from '~/components/user/types';
import { User } from '~/components/user/user';
import {
  get_dtx_members,
  fetchUsers,
  getGames,
  getTeams,
  getTournaments,
  fetchCurrentUser,
} from '~/components/api/api';
import type {
  GameType,
  TeamType,
  TournamentType,
} from '~/components/tournament/types';
import { createCookie } from 'react-router';
import { useMemo } from 'react';
import React, { memo } from 'react';
import axios from '~/components/api/axios';
import type { Tournament } from '~/components/tournament/tournament';

interface UserState {
  currentUser: UserType;
  selectedUser: UserType;
  hasHydrated: boolean;
  setHasHydrated: (hydrated: boolean) => void;
  setCurrentUser: (user: UserType) => void;
  clearUser: () => void;
  isStaff: () => boolean;
  selectedDiscordUser: GuildMember;
  setDiscordUser: (discordUser: GuildMember) => void;
  discordUsers: GuildMembers;
  getDiscordUsers: () => Promise<void>;
  setDiscordUsers: (users: GuildMembers) => void;
  users: UserType[];
  setUsers: (users: UserType[]) => void;
  setUser: (user: UserType) => void;
  addUser: (user: UserType) => void;
  delUser: (user: UserType) => void;
  getUsers: () => Promise<void>;
  createUser: (user: UserType) => Promise<void>;

  clearUsers: () => void;
  game: GameType;
  games: GameType[];
  team: TeamType;
  teams: TeamType[];
  tournament: TournamentType;
  tournaments: TournamentType[];

  resetSelection: () => void;
  setGames: (games: GameType[]) => void;
  setTeams: (teams: TeamType[]) => void;
  setTeam: (teams: TeamType) => void;
  addTournament: (tourn: TournamentType) => void;
  delTournament: (tourn: TournamentType) => void;

  setTournaments: (tournaments: TournamentType[]) => void;
  setTournament: (tournament: TournamentType) => void;
  tournamentsByUser: (user: UserType) => TournamentType[];
  getCurrentUser: () => Promise<void>;
  userAPIError: any;
  tournamentPK: number | null;
  getTournaments: () => Promise<void>;
  getTeams: () => Promise<void>;
  getGames: () => Promise<void>;
  getCurrentTournament: () => Promise<void>;
}
export const useUserStore = create<UserState>()(
  persist(
    (set, get) => ({
      tournament: {} as TournamentType,
      tournaments: [] as TournamentType[],
      game: {} as GameType,
      games: [] as GameType[],
      teams: [] as TeamType[],
      team: {} as TeamType,
      currentUser: new User({} as UserType),
      selectedUser: {} as UserType,
      resetSelection: () => {
        set({ selectedUser: {} as UserType });
        set({ selectedDiscordUser: {} as GuildMember });
      },
      getDiscordUsers: async () => {
        try {
          console.log('User fetching');
          get_dtx_members()
            .then((response) => {
              get().setDiscordUsers(response);
            })
            .catch((error) => {
              console.error('Error fetching user:', error);

              get().setDiscordUsers([] as GuildMembers);
            });
        } catch (err) {
          get().setDiscordUsers([] as GuildMembers);
        } finally {
        }
      },

      selectedDiscordUser: {} as GuildMember,
      setDiscordUser: (discordUser) =>
        set({ selectedDiscordUser: discordUser }),
      discordUsers: [] as GuildMembers,
      setDiscordUsers: (discordUsers: GuildMembers) => set({ discordUsers }),
      setCurrentUser: (user) => {
        console.log('User set:', user);

        set({ currentUser: user });
      },
      setUser: (user: UserType) => {
        console.log('User set:', user);
        if (!user) {
          console.error('Attempted to set user to null or undefined');
          return;
        }
        if (user.pk === undefined) {
          console.error('User pk is undefined:', user);
          return;
        }
        const users = get().users;
        const userIndex = users.findIndex((u) => u.pk === user.pk);
        if (userIndex !== -1) {
          const updatedUsers = [...users];
          updatedUsers[userIndex] = user;
          set({ users: updatedUsers });
          console.log('userUserStore updated User', user);
        } else {
          get().addUser(user);
        }
      },
      clearUser: () => set({ currentUser: {} as UserType }),
      isStaff: () => !!get().currentUser?.is_staff,
      users: [] as UserType[],
      addUser: (user) => set({ users: [...get().users, user] }),

      addTournament: (tourn: TournamentType) =>
        set({ tournaments: [...get().tournaments, tourn] }),
      delTournament: (tourn: TournamentType) =>
        set({
          tournaments: get().tournaments.filter((t) => t.pk !== tourn.pk),
        }),

      delUser: (user) =>
        set({ users: get().users.filter((u) => u.pk !== user.pk) }),

      setUsers: (users) => set({ users }),
      clearUsers: () => set({ users: [] as UserType[] }),

      getUsers: async () => {
        try {
          const response = await fetchUsers();
          set({ users: response });
          console.log('User fetched successfully:', response);
        } catch (error) {
          console.error('Error fetching users:', error);
        }
      },

      getCurrentUser: async () => {
        try {
          const response = await fetchCurrentUser();
          set({ currentUser: response });
          console.log('User fetched successfully:', response);
        } catch (error) {
          console.log('No User logged in:', error);
          set({ currentUser: {} as UserType });
        }
      },

      setTournaments: (tournaments) => set({ tournaments }),
      setTournament: (tournament) => set({ tournament }),
      tournamentsByUser: (user) =>
        get().tournaments.filter(
          (tournament) => tournament?.users === user?.pk,
        ),
      setGames: (games) => set({ games }),
      getGames: async () => {
        try {
          const response = await getGames();
          set({ games: response as GameType[] });
          console.log('Games fetched successfully:', response);
        } catch (error) {
          console.error('Error fetching games:', error);
        }
      },
      getTeams: async () => {
        try {
          const response = await getTeams();
          set({ games: response as TeamType[] });
          console.log('Games fetched successfully:', response);
        } catch (error) {
          console.error('Error fetching games:', error);
        }
      },
      setTournamentPK: (pk: number) => set({ tournamentPK: pk }),
      tournamentPK: null,
      getCurrentTournament: async () => {
        if (get().tournamentPK) {
          try {
            const response = await axios.get(
              `/tournaments/${get().tournamentPK}/`,
            );
            set({ tournament: response.data });
          } catch (err) {
            console.error('Failed to fetch tournament:', err);
          }
        }
      },
      getTournaments: async () => {
        try {
          const response = await getTournaments();
          set({ tournaments: response as TournamentType[] });
          console.log('Tournaments fetched successfully:', response);
        } catch (error) {
          console.error('Error fetching tournaments:', error);
        }
      },

      setTeams: (teams: TeamType[]) => set({ teams }),

      setTeam: (team: TeamType) => set({ team }),
      hasHydrated: false,

      createUser: async (user: UserType) => {
        try {
          //set({ users: response });
          // console.log('User fetched successfully:', response);
        } catch (error) {
          console.error('Error fetching users:', error);
        }
      },
      setHasHydrated: (hydrated) => set({ hasHydrated: hydrated }),

      userAPIError: null,
      setUserAPIError: (error: any) => set({ userAPIError: error }),
      clearUserAPIError: () => set({ userAPIError: null }),
    }),
    {
      name: 'dtx-storage', // key in localStorage
      partialize: (state) => ({
        currentUser: state.currentUser,
        users: state.users,
      }), // optionally limit what's stored
      onRehydrateStorage: () => (state) => {
        console.log('Rehydrating user store...');
        console.log('Current user:', state?.currentUser);
        if (state?.currentUser.username === undefined) {
          state?.getCurrentUser();
        }
        state?.setHasHydrated(true);
      },
      storage: createJSONStorage(() => sessionStorage), // (optional) by default, 'localStorage' is used
      skipHydration: false, // (optional) if you want to skip hydration
    },
  ),
);
