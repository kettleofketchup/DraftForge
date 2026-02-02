/**
 * Organization Store
 *
 * Zustand store for current organization context.
 * Used to provide organization context across components.
 */

import { create } from 'zustand';
import { fetchOrganization, getOrganizationUsers } from '~/components/api/api';
import type { OrganizationType } from '~/components/organization/schemas';
import type { UserType } from '~/index';
import { getLogger } from '~/lib/logger';

const log = getLogger('orgStore');

interface OrgState {
  /** Current organization context */
  currentOrg: OrganizationType | null;
  currentOrgLoading: boolean;

  /** Organization users (members via OrgUser) */
  orgUsers: UserType[];
  orgUsersLoading: boolean;
  orgUsersError: string | null;
  orgUsersOrgId: number | null;

  /** Actions */
  setCurrentOrg: (org: OrganizationType | null) => void;
  getOrganization: (orgPk: number) => Promise<void>;
  reset: () => void;

  /** Org Users Actions */
  setOrgUsers: (users: UserType[]) => void;
  getOrgUsers: (orgId: number) => Promise<void>;
  clearOrgUsers: () => void;
}

export const useOrgStore = create<OrgState>((set, get) => ({
  currentOrg: null,
  currentOrgLoading: false,
  orgUsers: [],
  orgUsersLoading: false,
  orgUsersError: null,
  orgUsersOrgId: null,

  setCurrentOrg: (org) => set({ currentOrg: org }),

  getOrganization: async (orgPk: number) => {
    // Skip if already loaded for this org
    if (get().currentOrg?.pk === orgPk) {
      log.debug('Organization already loaded:', orgPk);
      return;
    }

    set({ currentOrgLoading: true });

    try {
      const org = await fetchOrganization(orgPk);
      set({ currentOrg: org, currentOrgLoading: false });
      log.debug('Organization fetched successfully:', org.name);
    } catch (error) {
      log.error('Error fetching organization:', error);
      set({ currentOrg: null, currentOrgLoading: false });
    }
  },

  reset: () =>
    set({
      currentOrg: null,
      currentOrgLoading: false,
      orgUsers: [],
      orgUsersLoading: false,
      orgUsersOrgId: null,
      orgUsersError: null,
    }),

  setOrgUsers: (users) => set({ orgUsers: users }),

  getOrgUsers: async (orgId: number) => {
    // Skip if already loaded for this org
    if (get().orgUsersOrgId === orgId && get().orgUsers.length > 0) {
      log.debug('OrgUsers already loaded for org:', orgId);
      return;
    }

    set({ orgUsersLoading: true, orgUsersError: null, orgUsersOrgId: orgId });

    try {
      const users = await getOrganizationUsers(orgId);
      set({ orgUsers: users, orgUsersLoading: false });
      log.debug('OrgUsers fetched successfully:', users.length, 'users');
    } catch (error) {
      log.error('Error fetching org users:', error);
      set({
        orgUsersError:
          error instanceof Error ? error.message : 'Failed to fetch org users',
        orgUsersLoading: false,
        orgUsers: [],
      });
    }
  },

  clearOrgUsers: () =>
    set({ orgUsers: [], orgUsersOrgId: null, orgUsersError: null }),
}));

// Selectors
export const orgSelectors = {
  /** Get current org name */
  orgName: (s: OrgState) => s.currentOrg?.name ?? null,

  /** Get current org pk */
  orgPk: (s: OrgState) => s.currentOrg?.pk ?? null,

  /** Check if org is set */
  hasOrg: (s: OrgState) => s.currentOrg !== null,

  /** Get org users */
  orgUsers: (s: OrgState) => s.orgUsers,

  /** Check if org users are loading */
  isLoadingOrgUsers: (s: OrgState) => s.orgUsersLoading,
};
