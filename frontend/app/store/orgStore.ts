/**
 * Organization Store
 *
 * Zustand store for current organization context.
 * Used to provide organization context across components.
 */

import { create } from 'zustand';
import type { OrganizationType } from '~/components/organization/schemas';

interface OrgState {
  /** Current organization context */
  currentOrg: OrganizationType | null;

  /** Actions */
  setCurrentOrg: (org: OrganizationType | null) => void;
  reset: () => void;
}

export const useOrgStore = create<OrgState>((set) => ({
  currentOrg: null,

  setCurrentOrg: (org) => set({ currentOrg: org }),

  reset: () => set({ currentOrg: null }),
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
