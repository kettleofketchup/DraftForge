import { create } from 'zustand';
import { persist, createJSONStorage,  } from 'zustand/middleware';
import type { GuildMember, UserType, GuildMembers, UsersType } from '~/components/user/types';
import { User } from '~/components/user/user';
import { get_dtx_members,fetchUsers, getGames, getTeams, getTournaments, fetchCurrentUser} from "~/components/api/api";
import type { GameType, TeamType, TournamentType } from '~/components/tournament/types';
import { createCookie } from 'react-router';
import { useMemo } from 'react';
import React, { memo } from 'react';

interface UserState {
    currentUser: UserType;
    selectedUser: UserType;
    hasHydrated: boolean,
    setHasHydrated: (hydrated: boolean) => void;
    setUser: (user: UserType) => void;
    clearUser: () => void;
    isStaff: () => boolean;
    selectedDiscordUser: GuildMember;
    setDiscordUser: (discordUser:GuildMember)  => void;
    discordUsers: GuildMembers;
    setDiscordUsers: (users:GuildMembers)  => void;
    users: UserType[] ;
    setUsers: (uses: UserType[]) => void;
    addUser: (user: UserType) => void;
    clearUsers: () => void;
    game: GameType;
    games: GameType[];
    team: TeamType;
    teams: TeamType[];
    tournament: TournamentType;
    tournaments: TournamentType[];
    getUsers: () => Promise<void>;
    resetSelection: () => void;
    setGames: (games: GameType[]) => void;
    setTeams: (teams: TeamType[]) => void;
    setTeam: (teams: TeamType) => void;

    setTournaments: (tournaments: TournamentType[]) => void;
    setTournament: (tournament: TournamentType) => void;
    tournamentsByUser: (user: UserType) => TournamentType[];
    getCurrentUser: () => Promise<void>;
    createUser: (user:UserType) => Promise<void>;
    userAPIError: any ;

    getTournaments: () => Promise<void>;
    getTeams: () => Promise<void>;
    getGames: () => Promise<void>;


}
export const useUserStore = create<UserState>()(
    persist((set, get) => ({
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
      selectedDiscordUser: {} as GuildMember,
      setDiscordUser: (discordUser) =>set({ selectedDiscordUser: discordUser }),
      discordUsers: [] as GuildMembers,
      setDiscordUsers: (discordUsers: GuildMembers) => set({ discordUsers }),
      setUser: (user) => {
        console.log('User set:', user);

        set({ currentUser: user })},
      clearUser: () => set({ currentUser: {} as UserType }),
      isStaff: () => !!get().currentUser?.is_staff,
      users: [] as UserType[],
      addUser: (user) => set({users: [...get().users, user]}),
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
            console.error('Error fetching users:', error);
            set({ currentUser: {} as UserType });
          }
        },

        setTournaments: (tournaments) => set({ tournaments }),
        setTournament: (tournament) => set({ tournament }),
        tournamentsByUser: (user) => get().tournaments.filter((tournament) => tournament.users === user.pk),
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
        getTournaments: async () => {
          try {
            const response = await getTournaments();
            set({ tournaments: response as TeamType[] });
            console.log('Games fetched successfully:', response);
          } catch (error) {
            console.error('Error fetching games:', error);
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
        setUserAPIError: (error:any) => set({ userAPIError: error }),
        clearUserAPIError: () => set({ userAPIError: null }),
      }),
      {
          name: 'dtx-storage', // key in localStorage
          partialize: (state) => ({ currentUser: state.currentUser }), // optionally limit what's stored
          onRehydrateStorage: () => (state) => {
                state?.setHasHydrated(true);
          },
          storage: createJSONStorage(() => sessionStorage), // (optional) by default, 'localStorage' is used
          skipHydration: false, // (optional) if you want to skip hydration
      }
    )
);
