import { leagueInfo, parseFilterId } from '~/components/tournament/tournamentBuckets';
import type { TournamentBucket, TournamentType } from '~/components/tournament/types';

export const ORG_SCOPE_MINE = 'mine';
export const ORG_SCOPE_ALL = 'all';

export type OrgScope = { kind: 'mine' } | { kind: 'all' } | { kind: 'org'; id: number };

export interface OrgScopeRequest {
  organization?: number;
  mine?: boolean;
  memberOrgIds?: number[];
  openSignups?: boolean;
}

export function defaultOrgScope(isLoggedIn: boolean): OrgScope {
  return isLoggedIn ? { kind: 'mine' } : { kind: 'all' };
}

/** `?organization=` value: mine | all | <id>; anything else means the default. */
export function parseOrgScope(raw: string | null, isLoggedIn: boolean): OrgScope {
  if (raw === ORG_SCOPE_ALL) return { kind: 'all' };
  const id = parseFilterId(raw);
  if (id !== undefined) return { kind: 'org', id };
  return defaultOrgScope(isLoggedIn);
}

/** Whether the param picks a scope without knowing who is logged in. */
export function isExplicitOrgScope(raw: string | null): boolean {
  return raw === ORG_SCOPE_ALL || parseFilterId(raw) !== undefined;
}

export function orgScopeValue(scope: OrgScope): string {
  return scope.kind === 'org' ? String(scope.id) : scope.kind;
}

export function isDefaultOrgScope(scope: OrgScope, isLoggedIn: boolean): boolean {
  return scope.kind === defaultOrgScope(isLoggedIn).kind;
}

/** URL value for a selected option: null (drop the param) for the default. */
export function orgScopeParam(value: string, isLoggedIn: boolean): string | null {
  return value === orgScopeValue(defaultOrgScope(isLoggedIn)) ? null : value;
}

export function orgScopeRequest(
  scope: OrgScope,
  bucket: TournamentBucket,
  memberOrgIds: readonly number[] | undefined,
): OrgScopeRequest {
  if (scope.kind === 'org') return { organization: scope.id };
  if (scope.kind === 'all') return {};
  const mine = { mine: true, memberOrgIds: [...(memberOrgIds ?? [])].sort((a, b) => a - b) };
  // Signups only matter for what is still ahead.
  return bucket === 'upcoming' ? { ...mine, openSignups: true } : mine;
}

export function groupOrganizations<T extends { pk?: number | null }>(
  orgs: readonly T[],
  memberOrgIds: readonly number[] | undefined,
): { yours: T[]; others: T[] } {
  const member = new Set(memberOrgIds ?? []);
  const yours: T[] = [];
  const others: T[] = [];
  for (const org of orgs) {
    if (org.pk == null) continue;
    if (member.has(org.pk)) yours.push(org);
    else others.push(org);
  }
  return { yours, others };
}

/** An open-signup tournament that is listed only because its signups are open. */
export function showsSignupsOpenBadge(
  t: TournamentType,
  memberOrgIds: readonly number[] | undefined,
): boolean {
  if (t.signups_open !== true) return false;
  const orgId = leagueInfo(t)?.organization_id;
  return orgId == null || !(memberOrgIds ?? []).includes(orgId);
}
