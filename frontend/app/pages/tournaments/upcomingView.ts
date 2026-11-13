import { splitByMembership } from '~/components/tournament/tournamentBuckets';
import type {
  TournamentBucket,
  TournamentType,
} from '~/components/tournament/types';

export function coerceTab(raw: string | null | undefined): TournamentBucket {
  return raw === 'archived' ? 'archived' : 'upcoming';
}

export type UpcomingView =
  | { kind: 'skeleton' }
  | { kind: 'empty' }
  | { kind: 'flat'; items: TournamentType[] }
  | { kind: 'tiers'; yours: TournamentType[]; others: TournamentType[] };

export interface UpcomingViewInput {
  data: TournamentType[] | undefined;
  membershipPending: boolean;
  isLoggedIn: boolean;
  memberOrgIds: number[] | undefined;
  orgOrLeagueFilter: boolean;
}

export function resolveUpcomingView({
  data,
  membershipPending,
  isLoggedIn,
  memberOrgIds,
  orgOrLeagueFilter,
}: UpcomingViewInput): UpcomingView {
  if (data === undefined || membershipPending) return { kind: 'skeleton' };
  if (data.length === 0) return { kind: 'empty' };
  if (isLoggedIn && !orgOrLeagueFilter && memberOrgIds?.length) {
    return { kind: 'tiers', ...splitByMembership(data, memberOrgIds) };
  }
  return { kind: 'flat', items: data };
}
