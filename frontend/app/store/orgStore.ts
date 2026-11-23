/**
 * Organization Store
 *
 * Zustand store for current organization context.
 * Used to provide organization context across components.
 */

import { create } from 'zustand';
import { fetchOrganization } from '~/components/api/api';
import type { OrganizationType } from '~/components/organization/schemas';
import { getLogger } from '~/lib/logger';

const log = getLogger('orgStore');

interface OrgState {
  /** Current organization context */
  currentOrg: OrganizationType | null;
  currentOrgLoading: boolean;

  /** Actions */
  setCurrentOrg: (org: OrganizationType | null) => void;
  getOrganization: (orgPk: number) => Promise<void>;
  reset: () => void;
}

export const useOrgStore = create<OrgState>((set, get) => ({
  currentOrg: null,
  currentOrgLoading: false,

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
    set({ currentOrg: null, currentOrgLoading: false });
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
};
