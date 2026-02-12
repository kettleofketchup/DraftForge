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
import type { DraftRoundType, DraftType } from '~/components/teamdraft/types';
import type { LeagueType } from '~/components/league/schemas';
import type { OrganizationType } from '~/components/organization/schemas';
import type { TeamType, TournamentType } from '~/components/tournament/types';
import { User } from '~/components/user/user';
import type { GameType, GuildMember, GuildMembers, UserType } from '~/index';
import { getLogger } from '~/lib/logger';
import { useUserCacheStore } from '~/store/userCacheStore';

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
  /** Global user pk array (resolved via useResolvedUsers hook) */
  globalUserPks: number[];
  /** Upsert a user into the cache (replaces old array-based setUser) */
  setUser: (user: UserType) => void;
  /** Add a user to cache + global pk array */
  addUser: (user: UserType) => void;
  /** Remove a user from cache + global pk array */
  delUser: (user: UserType) => void;
  getUsers: () => Promise<void>;
  createUser: (user: UserType) => Promise<void>;
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
  organizationPk: number | null; // Track which org is loaded
  organizationsLoaded: boolean; // Track if orgs list is loaded
  setOrganizations: (orgs: OrganizationType[]) => void;
  setOrganization: (org: OrganizationType | null) => void;
  getOrganizations: () => Promise<void>;
  getOrganization: (pk: number, force?: boolean) => Promise<void>;

  // Leagues
  leagues: LeagueType[];
  league: LeagueType | null;
  leaguesOrgId: number | null | 'all'; // Track which org's leagues are loaded ('all' for no filter)
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

      clearUser: () => {
        set({ currentUser: {} as UserType });
        useUserCacheStore.getState().reset();
      },
      isStaff: () => !!get().currentUser?.is_staff,
      globalUserPks: [] as number[],

      setUser: (user: UserType) => {
        if (!user || user.pk == null) return;
        useUserCacheStore.getState().upsert(user);
        // Also update tournament user references
        const tournaments = get().tournamentsByUser(user);
        for (const tournament of tournaments) {
          let change = false;
          tournament.users = tournament.users?.map((u) => {
            if (u?.pk === user.pk) { change = true; return user; }
            return u;
          }) ?? null;
          if (change) get().setTournament(tournament);
        }
      },

      addUser: (user: UserType) => {
        if (!user || user.pk == null) return;
        useUserCacheStore.getState().upsert(user);
        const pks = get().globalUserPks;
        if (!pks.includes(user.pk!)) {
          set({ globalUserPks: [...pks, user.pk!] });
        }
      },

      delUser: (user: UserType) => {
        if (!user || user.pk == null) return;
        useUserCacheStore.getState().remove(user.pk!);
        set({ globalUserPks: get().globalUserPks.filter((pk) => pk !== user.pk) });
      },

      addTournament: (tourn: TournamentType) =>
        set({ tournaments: [...get().tournaments, tourn] }),
      delTournament: (tourn: TournamentType) =>
        set({
          tournaments: get().tournaments.filter((t) => t?.pk !== tourn.pk),
        }),

      getUsers: async () => {
        try {
          const response = await fetchUsers();
          useUserCacheStore.getState().upsert(response);
          set({
            globalUserPks: response.filter((u) => u.pk != null).map((u) => u.pk!),
          });
          log.debug('Users fetched successfully:', response.length);
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
        if (!tournament) return; // Guard against null tournament
        set({ tournament });
        // If a tournament with the same pk exists in tournaments, update it
        set((state) => {
          const idx = state.tournaments.findIndex(
            (t) => t?.pk === tournament.pk,
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
            tournament.users.some((u) => u?.pk === user?.pk),
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
      organizationPk: null,
      organizationsLoaded: false,
      setOrganizations: (orgs) => set({ organizations: orgs, organizationsLoaded: true }),
      setOrganization: (org) => set({ organization: org, organizationPk: org?.pk ?? null }),
      getOrganizations: async () => {
        // Skip if already loaded
        if (get().organizationsLoaded && get().organizations.length > 0) {
          log.debug('Organizations already loaded, skipping fetch');
          return;
        }
        try {
          const response = await getOrganizations();
          set({ organizations: response, organizationsLoaded: true });
          log.debug('Organizations fetched successfully:', response);
        } catch (error) {
          log.error('Error fetching organizations:', error);
        }
      },
      getOrganization: async (pk: number, force = false) => {
        // Skip if already loaded for this pk (unless forced)
        if (!force && get().organizationPk === pk && get().organization) {
          log.debug('Organization already loaded:', pk);
          return;
        }
        try {
          const response = await fetchOrganization(pk);
          set({ organization: response, organizationPk: pk });
          log.debug('Organization fetched successfully:', response);
        } catch (error) {
          log.error('Error fetching organization:', error);
          set({ organization: null, organizationPk: null });
        }
      },

      // Leagues
      leagues: [] as LeagueType[],
      league: null,
      leaguesOrgId: null,
      setLeagues: (leagues) => set({ leagues }),
      setLeague: (league) => set({ league }),
      getLeagues: async (orgId?: number) => {
        const targetOrgId = orgId ?? 'all';
        // Skip if already loaded for this org
        if (get().leaguesOrgId === targetOrgId && get().leagues.length > 0) {
          log.debug('Leagues already loaded for org:', targetOrgId);
          return;
        }
        try {
          const response = await getLeagues(orgId);
          set({ leagues: response, leaguesOrgId: targetOrgId });
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
      }),
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
