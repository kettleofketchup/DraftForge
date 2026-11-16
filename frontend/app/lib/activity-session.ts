import type { UserType } from '~/index';
import type { ActivityDraftKind, ActivityView } from '~/lib/activity-types';
import type { DraftActivitySession } from '~/lib/discord';

/** Activity credentials stay in memory and are never sent to unrelated APIs. */
export interface ActivityCredential {
  token: string;
  scope: 'tournament' | 'draft';
  tournament_id: number | null;
  pin: ActivityView | null;
  site_url: string;
  user?: UserType;
}

export const REFRESH_MIN_INTERVAL_MS = 30_000;
export const REFRESH_WINDOW_MS = 600_000;
export const REFRESH_WINDOW_MAX = 3;

// Mirrors HERO_SUFFIXES in backend/discordbot/activity_auth.py.
const HERO_SUFFIXES = new Set([
  'set-ready',
  'trigger-roll',
  'submit-choice',
  'submit-pick',
  'list-events',
  'list-available-heroes',
  'pause',
  'resume',
]);
const IDENTITY_PATHS = new Set([
  '/current_user',
  '/discord/activity/drafts/',
  '/discord/activity/views/',
]);
const TEAM_BODY_PATHS = new Set([
  '/tournaments/pick_player',
  '/tournaments/undo-pick',
  '/draft/get-style-mmrs',
]);
const HERO_PATH = /^\/herodraft\/(\d+)\/(?:([a-z-]+)\/)?$/;
const TEAM_PATH = /^\/draft\/(\d+)\/(?:ready|start|pause|resume)\/$/;

let session: ActivityCredential | null = null;
let refresher: (() => Promise<void>) | null = null;
let refreshing: Promise<boolean> | null = null;
let refreshExhausted: (() => void) | null = null;
let refreshTimes: number[] = [];

export function toActivityCredential(
  value: DraftActivitySession,
): ActivityCredential {
  const scope = value.scope === 'tournament' ? 'tournament' : 'draft';
  return {
    token: value.token,
    scope,
    tournament_id: value.tournament_id ?? null,
    pin: scope === 'draft' ? { kind: value.kind, id: value.draft_id } : null,
    site_url: value.site_url ?? window.location.origin,
    user: value.user,
  };
}
export function setActivityCredential(value: ActivityCredential | null) {
  session = value;
}
export function getActivityCredential(): ActivityCredential | null {
  return session;
}
export function getActivityUser(): UserType | undefined {
  return session?.user;
}
export function isActivityFrame(): boolean {
  return (
    typeof window !== 'undefined' &&
    window.location.pathname.startsWith('/activity')
  );
}

/** The Activity route re-runs the Discord handshake when a credential is rejected. */
export function setActivityRefresher(value: (() => Promise<void>) | null) {
  refresher = value;
  refreshTimes = [];
}
export function setActivityRefreshExhausted(fn: (() => void) | null) {
  refreshExhausted = fn;
}
/** Concurrent callers share one re-handshake; resolves false if it failed or was throttled. */
export function refreshActivityCredential(): Promise<boolean> {
  if (refreshing) return refreshing;
  if (!refresher) return Promise.resolve(false);
  const now = Date.now();
  refreshTimes = refreshTimes.filter((at) => now - at < REFRESH_WINDOW_MS);
  const last = refreshTimes.at(-1);
  if (last !== undefined && now - last < REFRESH_MIN_INTERVAL_MS)
    return Promise.resolve(false);
  if (refreshTimes.length >= REFRESH_WINDOW_MAX) {
    refreshExhausted?.();
    return Promise.resolve(false);
  }
  refreshTimes.push(now);
  refreshing = refresher()
    .then(
      () => true,
      () => false,
    )
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

function inScope(kind: ActivityDraftKind, id: number): boolean {
  if (!session || id <= 0) return false;
  if (session.scope === 'tournament') return true;
  return session.pin?.kind === kind && session.pin.id === id;
}
export function activityAuthorization(path: string): string | undefined {
  if (!session) return;
  const header = `DraftActivity ${session.token}`;
  if (IDENTITY_PATHS.has(path)) return header;
  const hero = HERO_PATH.exec(path);
  if (hero) {
    if (hero[2] !== undefined && !HERO_SUFFIXES.has(hero[2])) return;
    return inScope('hero', Number(hero[1])) ? header : undefined;
  }
  const team = TEAM_PATH.exec(path);
  if (team) return inScope('team', Number(team[1])) ? header : undefined;
  if (
    TEAM_BODY_PATHS.has(path) &&
    (session.scope === 'tournament' || session.pin?.kind === 'team')
  )
    return header;
}
export function activitySocket(kind: ActivityDraftKind, id: number) {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const active = inScope(kind, id);
  const path = active
    ? `/api/discord/activity/${kind === 'hero' ? 'draft' : 'team-draft'}/${id}/`
    : `/api/${kind === 'hero' ? 'herodraft' : 'draft'}/${id}/`;
  return {
    url: `${protocol}//${window.location.host}${path}`,
    protocols: active ? ['draftactivity', session!.token] : undefined,
  };
}
/** Mirrors external_path in backend/discordbot/activity_menu.py. */
export function activityExternalUrl(view: ActivityView): string | undefined {
  if (!session) return;
  if (view.kind === 'hero') return `${session.site_url}/herodraft/${view.id}`;
  const tournament = session.tournament_id;
  if (tournament === null) return;
  if (view.kind === 'team')
    return `${session.site_url}/tournament/${tournament}/teams/draft`;
  return `${session.site_url}/tournament/${tournament}/bracket`;
}
