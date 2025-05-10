import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { GuildMember, UserType, GuildMembers } from '~/components/user/types';
import { User } from '~/components/user/user';
import { UsersPage } from '~/pages/users/users';
import { get_dtx_members,fetchUsers, getGames, getTeams, getTournaments, fetchCurrentUser} from "~/components/api/api";
import { useCallback } from 'react';
import type { GameType, TeamType, TournamentType } from '~/components/tournament/types';

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
    getUsers: () => Promise<void>;
    game: GameType;
    games: GameType[];
    team: TeamType;
    teams: TeamType[];
    tournament: TournamentType;
    tournaments: TournamentType[];

    setGames: (games: GameType[]) => void;
    setTeams: (teams: TeamType[]) => void;
    setTeam: (teams: TeamType) => void;

    setTournaments: (tournaments: TournamentType[]) => void;
    setTournament: (tournament: TournamentType) => void;
    tournamentsByUser: (user: UserType) => TournamentType[];
    getCurrentUser: () => Promise<void>;
    updateUser: (user:UserType) => Promise<void>;
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
            set({ user: response });
            console.log('User fetched successfully:', response);
          } catch (error) {
            console.error('Error fetching users:', error);
            set({ user: {} as UserType });
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

        updateUser: async (user: UserType) => {
          try {
            const response = await fetchUsers();
            set({ users: response });
            console.log('User fetched successfully:', response);
          } catch (error) {
            console.error('Error fetching users:', error);
          }
        },
        createUser: async (user: UserType) => {
          try {
            const response = await fetchUsers();
            set({ users: response });
            console.log('User fetched successfully:', response);
          } catch (error) {
            console.error('Error fetching users:', error);
          }
        },
        userAPIError: null,
        setUserAPIError: (error:any) => set({ userAPIError: error }),
        clearUserAPIError: () => set({ userAPIError: null }),
      }),
      {
          name: 'dtx-user-storage', // key in localStorage
          partialize: (state) => ({ user: state.user }), // optionally limit what's stored
      }
    )
);
