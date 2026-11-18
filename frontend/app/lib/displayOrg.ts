import type { QueryClient } from '@tanstack/react-query';
import { useSyncExternalStore } from 'react';
import { matchPath } from 'react-router';

import { useHeroDraftStore } from '~/store/heroDraftStore';
import { useLeagueStore } from '~/store/leagueStore';
import { useUserStore } from '~/store/userStore';

type OrgRef = { organization_pk?: number | null } | null | undefined;
type EventRef = { organization?: number | null } | null | undefined;

let queryClient: QueryClient | null = null;
const routeListeners = new Set<() => void>();

/** The app's query client, read for the tournament and event the current page shows. */
export function setDisplayOrgQueryClient(client: QueryClient | null): void {
  queryClient = client;
}

/** Called by the root after a navigation commits, so useDisplayOrgId subscribers recompute. */
export function notifyDisplayOrgRoute(): void {
  routeListeners.forEach((l) => l());
}

const toPk = (raw: string | undefined): number | null => {
  const n = raw ? parseInt(raw, 10) : NaN;
  return Number.isNaN(n) ? null : n;
};

const match = (pattern: string, path: string): number | null | undefined => {
  const m = matchPath(pattern, path);
  if (!m) return undefined;
  return toPk(Object.values(m.params)[0]);
};

function tournamentOrg(pk: number): number | null {
  const queried = queryClient?.getQueryData<OrgRef>(['tournament', pk]);
  if (queried) return queried.organization_pk ?? null;
  const loaded = useUserStore.getState().tournament;
  return loaded?.pk === pk ? (loaded.organization_pk ?? null) : null;
}

function heroDraftOrg(id: number | null): number | null {
  const draft = useHeroDraftStore.getState().draft;
  if (!draft || (id !== null && draft.id !== id)) return null;
  return draft.organization_pk ?? null;
}

function orgForPath(path: string): number | null {
  let pk: number | null | undefined;
  if ((pk = match('/organizations/:organizationId', path)) !== undefined) {
    return pk;
  }
  if ((pk = match('/tournament/:pk/*', path)) !== undefined) {
    return pk === null ? null : tournamentOrg(pk);
  }
  if ((pk = match('/leagues/:leagueId/:tab?', path)) !== undefined) {
    const league = useLeagueStore.getState().currentLeague;
    if (pk === null || league?.pk !== pk) return null;
    return league.organization?.pk ?? league.organization_id ?? null;
  }
  pk = match('/events/:eventId/:tab?', path);
  if (pk === undefined) pk = match('/rollcall/:eventId', path);
  if (pk !== undefined) {
    if (pk === null) return null;
    return (
      queryClient?.getQueryData<EventRef>(['event', pk])?.organization ?? null
    );
  }
  if ((pk = match('/herodraft/:id', path)) !== undefined) {
    return heroDraftOrg(pk);
  }
  if (matchPath('/activity', path)) {
    return (
      useUserStore.getState().tournament?.organization_pk ?? heroDraftOrg(null)
    );
  }
  return null;
}

/**
 * Org whose server nicknames names resolve against, derived from the current
 * URL and the entity that page has loaded. React Router pushes history before
 * rendering a navigation, so this is already correct while the new page renders.
 */
export function currentDisplayOrgId(): number | null {
  if (typeof window === 'undefined') return null;
  return orgForPath(window.location.pathname);
}

function subscribe(onChange: () => void): () => void {
  routeListeners.add(onChange);
  const unsubs = [
    useUserStore.subscribe(onChange),
    useHeroDraftStore.subscribe(onChange),
    useLeagueStore.subscribe(onChange),
    queryClient?.getQueryCache().subscribe(onChange),
  ];
  return () => {
    routeListeners.delete(onChange);
    unsubs.forEach((u) => u?.());
  };
}

const serverSnapshot = (): null => null;

export function useDisplayOrgId(): number | null {
  return useSyncExternalStore(subscribe, currentDisplayOrgId, serverSnapshot);
}
