import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import {
  fetchCurrentUser,
  fetchDraft,
  fetchOrganization,
  fetchTournament,
  fetchUsers,
  get_dtx_members,
  getGames,
  getLeagues,
  getOrganizations,
  getTeams,
  getTournaments,
  getTournamentsBasic,
} from '~/components/api/api';
import type { DraftRoundType, DraftType } from '~/components/draft/types';
import type { LeagueType } from '~/components/league/schemas';
import type { OrganizationType } from '~/components/organization/schemas';
import type { TeamType, TournamentType } from '~/components/tournament/types';
import { User } from '~/components/user/user';
import type { GameType, GuildMember, GuildMembers, UserType } from '~/index';
import { getLogger } from '~/lib/logger';

const log = getLogger('userStore');

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
  draft: DraftType;
  setDraft: (draft: DraftType) => void;
  tournaments: TournamentType[];
  curDraftRound: DraftRoundType;
  setCurDraftRound: (round: DraftRoundType) => void;

  resetSelection: () => void;
  setGames: (games: GameType[]) => void;
  setTeams: (teams: TeamType[]) => void;
  setTeam: (teams: TeamType) => void;
  addTournament: (tourn: TournamentType) => void;
  delTournament: (tourn: TournamentType) => void;
  userQuery: string;
  addUserQuery: string;

  discordUserQuery: string;
  setUserQuery: (query: string) => void;
  setAddUserQuery: (query: string) => void;
  setDiscordUserQuery: (query: string) => void;
  setTournaments: (tournaments: TournamentType[]) => void;
  setTournament: (tournament: TournamentType) => void;
  tournamentsByUser: (user: UserType) => TournamentType[];
  getCurrentUser: () => Promise<void>;
  userAPIError: any;
  tournamentPK: number | null;
  getTournaments: () => Promise<void>;
  getTournamentsBasic: () => Promise<void>;

  getTeams: () => Promise<void>;
  getGames: () => Promise<void>;
  getCurrentTournament: () => Promise<void>;
  getDraft: () => Promise<void>;
  getCurrentDraftRound: () => Promise<void>;
  draftIndex: number;
  setDraftIndex: (index: number) => void;
  autoRefreshDraft: (() => Promise<void>) | null;
  setAutoRefreshDraft: (refresh: (() => Promise<void>) | null) => void;

  // Organizations
  organizations: OrganizationType[];
  organization: OrganizationType | null;
  setOrganizations: (orgs: OrganizationType[]) => void;
  setOrganization: (org: OrganizationType | null) => void;
  getOrganizations: () => Promise<void>;
  getOrganization: (pk: number) => Promise<void>;

  // Leagues
  leagues: LeagueType[];
  league: LeagueType | null;
  setLeagues: (leagues: LeagueType[]) => void;
  setLeague: (league: LeagueType | null) => void;
  getLeagues: (orgId?: number) => Promise<void>;
}
export const useUserStore = create<UserState>()(
  persist(
    (set, get) => ({
      tournament: {} as TournamentType,
      draft: get()?.tournament?.draft as DraftType,
      autoRefreshDraft: null,
      setAutoRefreshDraft: (refresh) => set({ autoRefreshDraft: refresh }),
      getDraft: async () => {
        try {
          await get().getCurrentTournament();
          set({ draft: get().tournament.draft });
        } catch (err) {
          log.error('Failed to fetch draft:', err);
        }
      },
      getCurrentDraftRound: async () => {
        try {
          await get().getCurrentTournament();

          set({
            curDraftRound:
              get().tournament.draft?.draft_rounds?.[get().draftIndex],
          });
        } catch (err) {
          log.error('Failed to fetch draft:', err);
        }
      },
      draftIndex: 0,
      setDraftIndex: (index: number) => set({ draftIndex: index }),
      setDraft: (draft: DraftType) => set({ draft }),
      tournaments: [] as TournamentType[],
      game: {} as GameType,
      games: [] as GameType[],
      teams: [] as TeamType[],
      team: {} as TeamType,

      updateCurrentDraft: async () => {
        if (!get().draft.pk) {
          console.debug('Current draft does not have a primary key (pk).');
          return;
        }
        const draft = await fetchDraft(get().draft.pk!);
        set({ draft: draft });
      },
      curDraftRound: {} as DraftRoundType,

      setCurDraftRound: (round: DraftRoundType) =>
        set({ curDraftRound: round }),
      currentUser: new User({} as UserType),
      userQuery: '',
      addUserQuery: '',
      setAddUserQuery: (query: string) => set({ addUserQuery: query }),
      discordUserQuery: '',
      setUserQuery: (query: string) => set({ userQuery: query }),
      setDiscordUserQuery: (query: string) => set({ discordUserQuery: query }),
      selectedUser: {} as UserType,
      resetSelection: () => {
        set({ selectedUser: {} as UserType });
        set({ selectedDiscordUser: {} as GuildMember });
      },
      getDiscordUsers: async () => {
        try {
          log.debug('User fetching');
          get_dtx_members()
            .then((response) => {
              get().setDiscordUsers(response);
            })
            .catch((error) => {
              log.error('Error fetching user:', error);

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
        log.debug('User set:', user);

        set({ currentUser: user });
      },

      setUser: (user: UserType) => {
        log.debug('User set:', user);
        if (!user) {
          log.error('Attempted to set user to null or undefined');
          return;
        }
        if (user.pk === undefined) {
          log.error('User pk is undefined:', user);
          return;
        }
        const users = get().users;
        const userIndex = users.findIndex((u) => u.pk === user.pk);
        if (userIndex !== -1) {
          const updatedUsers = [...users];
          updatedUsers[userIndex] = user;
          set({ users: updatedUsers });
          log.debug('userUserStore updated User', user);
        } else {
          get().addUser(user);
        }
        const tournaments = get().tournamentsByUser(user);
        if (tournaments.length == 0) {
          return;
        }
        log.debug('User tournaments', tournaments);
        for (const tournament of tournaments) {
          var change = false;
          log.debug('User tournament: ', tournament.pk, user);

          tournament.users = tournament.users?.map((u) => {
            if (u.pk === user.pk) {
              log.debug('Updating user in tournament:', tournament.pk, user);
              change = true;
              return user;
            }
            return u;
          }) ?? null;
          log.debug('Updating tournament with user:', tournament.users, user);
          if (change) {
            log.debug('Setting tournament with updated user:', tournament);
            get().setTournament(tournament);
          }
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
          log.debug('User fetched successfully:', response);
        } catch (error) {
          log.error('Error fetching users:', error);
        }
      },

      getCurrentUser: async () => {
        try {
          const response = await fetchCurrentUser();
          set({ currentUser: response });
          log.debug('User fetched successfully:', response);
        } catch (error) {
          log.debug('No User logged in:', error);
          set({ currentUser: {} as UserType });
        }
      },

      setTournaments: (tournaments) => set({ tournaments }),
      setTournament: (tournament) => {
        set({ tournament });
        // If a tournament with the same pk exists in tournaments, update it
        set((state) => {
          const idx = state.tournaments.findIndex(
            (t) => t.pk === tournament.pk,
          );
          if (idx !== -1) {
            const updatedTournaments = [...state.tournaments];
            updatedTournaments[idx] = tournament;
            return { tournaments: updatedTournaments };
          }
          return {};
        });
      },
      tournamentsByUser: (user) => {
        var tourns = get().tournaments;
        if (tourns.length === 0) {
          if (get().tournament) tourns.push(get().tournament);
        }
        tourns = tourns.filter(
          (tournament) =>
            Array.isArray(tournament?.users) &&
            tournament.users.some((u) => u.pk === user?.pk),
        );

        return tourns;
      },
      setGames: (games) => set({ games }),
      getGames: async () => {
        try {
          const response = await getGames();
          set({ games: response as GameType[] });
          log.debug('Games fetched successfully:', response);
        } catch (error) {
          log.error('Error fetching games:', error);
        }
      },
      getTeams: async () => {
        try {
          const response = await getTeams();
          set({ games: response as TeamType[] });
          log.debug('Games fetched successfully:', response);
        } catch (error) {
          log.error('Error fetching games:', error);
        }
      },
      setTournamentPK: (pk: number) => set({ tournamentPK: pk }),
      tournamentPK: null,
      getCurrentTournament: async () => {
        let id = get().tournamentPK;
        if (id === null || id === undefined) {
          return;
        }

        try {
          const response = await fetchTournament(id);
          set({ tournament: response });
        } catch (err) {
          log.error('Failed to fetch tournament:', err);
        }
      },

      getTournaments: async () => {
        try {
          const response = await getTournaments();
          set({ tournaments: response as TournamentType[] });
          log.debug('Tournaments fetched successfully:', response);
        } catch (error) {
          log.error('Error fetching tournaments:', error);
        }
      },

      getTournamentsBasic: async () => {
        try {
          const response = await getTournamentsBasic();
          set({ tournaments: response as TournamentType[] });
          log.debug('TournamentsBasic fetched successfully:', response);
        } catch (error) {
          log.error('Error fetching tournaments:', error);
        }
      },
      setTeams: (teams: TeamType[]) => set({ teams }),

      setTeam: (team: TeamType) => set({ team }),
      hasHydrated: false,

      createUser: async (user: UserType) => {
        try {
          //set({ users: response });
          // log.debug('User fetched successfully:', response);
        } catch (error) {
          log.error('Error fetching users:', error);
        }
      },
      setHasHydrated: (hydrated) => set({ hasHydrated: hydrated }),

      userAPIError: null,
      setUserAPIError: (error: any) => set({ userAPIError: error }),
      clearUserAPIError: () => set({ userAPIError: null }),

      // Organizations
      organizations: [] as OrganizationType[],
      organization: null,
      setOrganizations: (orgs) => set({ organizations: orgs }),
      setOrganization: (org) => set({ organization: org }),
      getOrganizations: async () => {
        try {
          const response = await getOrganizations();
          set({ organizations: response });
          log.debug('Organizations fetched successfully:', response);
        } catch (error) {
          log.error('Error fetching organizations:', error);
        }
      },
      getOrganization: async (pk: number) => {
        try {
          const response = await fetchOrganization(pk);
          set({ organization: response });
          log.debug('Organization fetched successfully:', response);
        } catch (error) {
          log.error('Error fetching organization:', error);
          set({ organization: null });
        }
      },

      // Leagues
      leagues: [] as LeagueType[],
      league: null,
      setLeagues: (leagues) => set({ leagues }),
      setLeague: (league) => set({ league }),
      getLeagues: async (orgId?: number) => {
        try {
          const response = await getLeagues(orgId);
          set({ leagues: response });
          log.debug('Leagues fetched successfully:', response);
        } catch (error) {
          log.error('Error fetching leagues:', error);
        }
      },
    }),
    {
      name: 'dtx-storage', // key in localStorage
      partialize: (state) => ({
        currentUser: state.currentUser,
        users: state.users,
      }), // optionally limit what's stored
      onRehydrateStorage: () => (state) => {
        log.debug('Rehydrating user store...');
        log.debug('Current user:', state?.currentUser);
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
