import type {
  LeagueMinimal,
  TournamentBucket,
  TournamentType,
} from '~/components/tournament/types';

const DAY_MS = 24 * 60 * 60 * 1000;
const GRACE_DAYS = 2;
const SEARCH_MIN = 2;
const SEARCH_MAX = 64;

export type DisplayStateLabel =
  | 'Live'
  | 'Upcoming'
  | 'Awaiting results'
  | 'Past'
  | 'Past (not closed)';

export interface DisplayState {
  label: DisplayStateLabel;
  muted: boolean;
}

export function utcDayStart(now: Date): Date {
  return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
}

export function bucketCutoff(now: Date): Date {
  return new Date(utcDayStart(now).getTime() - GRACE_DAYS * DAY_MS);
}

export function cutoffDayKey(now: Date): string {
  return bucketCutoff(now).toISOString().slice(0, 10);
}

function playedAt(t: TournamentType): Date | null {
  return t.date_played ? new Date(t.date_played) : null;
}

export function clockBucket(t: TournamentType, now: Date): TournamentBucket {
  const date = playedAt(t);
  const open = t.state === 'future' || t.state === 'in_progress';
  return open && date !== null && date >= bucketCutoff(now) ? 'upcoming' : 'archived';
}

export function leagueInfo(t: TournamentType): LeagueMinimal | null {
  return typeof t.league === 'object' && t.league !== null ? t.league : null;
}

export function leagueId(t: TournamentType): number | null {
  if (typeof t.league === 'number') return t.league;
  return leagueInfo(t)?.pk ?? null;
}

export function isTournamentLive(
  t: TournamentType,
  now: Date,
  bucket?: TournamentBucket,
): boolean {
  return t.state === 'in_progress' && (bucket ?? clockBucket(t, now)) === 'upcoming';
}

export function displayState(
  t: TournamentType,
  now: Date,
  bucket?: TournamentBucket,
): DisplayState {
  const b = bucket ?? clockBucket(t, now);
  if (b === 'upcoming') {
    if (t.state === 'in_progress') return { label: 'Live', muted: false };
    const date = playedAt(t);
    if (date !== null && date < utcDayStart(now)) {
      return { label: 'Awaiting results', muted: true };
    }
    return { label: 'Upcoming', muted: false };
  }
  if (t.state === 'past') return { label: 'Past', muted: false };
  return { label: 'Past (not closed)', muted: true };
}

export function parseFilterId(raw: string | null): number | undefined {
  if (raw === null || !/^\d+$/.test(raw)) return undefined;
  const value = Number.parseInt(raw, 10);
  return value > 0 && Number.isSafeInteger(value) ? value : undefined;
}

export function splitByMembership(
  ts: TournamentType[],
  memberOrgIds: readonly number[] | undefined,
): { yours: TournamentType[]; others: TournamentType[] } {
  const member = new Set(memberOrgIds ?? []);
  const yours: TournamentType[] = [];
  const others: TournamentType[] = [];
  for (const t of ts) {
    const orgId = leagueInfo(t)?.organization_id;
    if (orgId != null && member.has(orgId)) yours.push(t);
    else others.push(t);
  }
  return { yours, others };
}

export function normalizeSearch(raw: string): string | undefined {
  const trimmed = raw.trim();
  return trimmed.length < SEARCH_MIN ? undefined : trimmed.slice(0, SEARCH_MAX);
}

export function dedupeByPk(ts: TournamentType[]): TournamentType[] {
  const seen = new Set<number>();
  return ts.filter((t) => {
    if (t.pk === null) return true;
    if (seen.has(t.pk)) return false;
    seen.add(t.pk);
    return true;
  });
}

export function filtersActive(f: {
  /** The organization scope differs from the viewer's default. */
  scopeChanged?: boolean;
  league?: number;
  searchInput: string;
}): boolean {
  return (
    f.scopeChanged === true ||
    f.league !== undefined ||
    normalizeSearch(f.searchInput) !== undefined
  );
}
