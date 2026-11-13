/**
 * Organization Store
 *
 * Zustand store for current organization context.
 * Used to provide organization context across components.
 */

import { create } from 'zustand';
import { fetchOrganization, getOrganizationUsers } from '~/components/api/api';
import type { OrganizationType } from '~/components/organization/schemas';
import { getLogger } from '~/lib/logger';
import { useUserCacheStore } from '~/store/userCacheStore';

// Bumped per request and on clear so a superseded response is dropped.
let orgUsersRequest = 0;

const log = getLogger('orgStore');

interface OrgState {
  /** Current organization context */
  currentOrg: OrganizationType | null;
  currentOrgLoading: boolean;

  /** Organization user pks (resolved via useOrgUsers hook) */
  orgUserPks: number[];
  orgUsersLoading: boolean;
  orgUsersError: string | null;
  orgUsersOrgId: number | null;

  /** Actions */
  setCurrentOrg: (org: OrganizationType | null) => void;
  getOrganization: (orgPk: number) => Promise<void>;
  reset: () => void;

  /** Org Users Actions */
  getOrgUsers: (orgId: number) => Promise<void>;
  clearOrgUsers: () => void;
}

export const useOrgStore = create<OrgState>((set, get) => ({
  currentOrg: null,
  currentOrgLoading: false,
  orgUserPks: [],
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

  reset: () => {
    orgUsersRequest++;
    set({
      currentOrg: null,
      currentOrgLoading: false,
      orgUserPks: [],
      orgUsersLoading: false,
      orgUsersOrgId: null,
      orgUsersError: null,
    });
  },

  getOrgUsers: async (orgId: number) => {
    // Skip if already loaded for this org
    if (get().orgUsersOrgId === orgId && get().orgUserPks.length > 0) {
      log.debug('OrgUsers already loaded for org:', orgId);
      return;
    }

    if (get().orgUsersLoading && get().orgUsersOrgId === orgId) return;

    const request = ++orgUsersRequest;
    set({ orgUsersLoading: true, orgUsersError: null, orgUsersOrgId: orgId, orgUserPks: [] });

    try {
      const users = await getOrganizationUsers(orgId);
      if (request !== orgUsersRequest) return;
      useUserCacheStore.getState().upsert(users, { orgId });
      set({
        orgUserPks: users.filter((u) => u.pk != null).map((u) => u.pk!),
        orgUsersLoading: false,
      });
      log.debug('OrgUsers fetched successfully:', users.length, 'users');
    } catch (error) {
      if (request !== orgUsersRequest) return;
      log.error('Error fetching org users:', error);
      set({
        orgUsersError:
          error instanceof Error ? error.message : 'Failed to fetch org users',
        orgUsersLoading: false,
        orgUserPks: [],
      });
    }
  },

  clearOrgUsers: () => {
    orgUsersRequest++;
    set({ orgUserPks: [], orgUsersOrgId: null, orgUsersError: null, orgUsersLoading: false });
  },
}));

// Selectors
export const orgSelectors = {
  /** Get current org name */
  orgName: (s: OrgState) => s.currentOrg?.name ?? null,

  /** Get current org pk */
  orgPk: (s: OrgState) => s.currentOrg?.pk ?? null,

  /** Check if org is set */
  hasOrg: (s: OrgState) => s.currentOrg !== null,

  /** Check if org users are loading */
  isLoadingOrgUsers: (s: OrgState) => s.orgUsersLoading,
};
