import type { UserType } from '~/index';

/** Activity credentials stay in memory and are never sent to unrelated APIs. */
export interface ActivityCredential {
  token: string;
  draft_id: number;
  kind: 'hero' | 'team';
  user?: UserType;
}
let session: ActivityCredential | null = null;
let refresher: (() => Promise<void>) | null = null;
let refreshing: Promise<boolean> | null = null;
export function setActivityCredential(value: ActivityCredential | null) {
  session = value;
}
/** The Activity route re-runs the Discord handshake when a socket reports 4401. */
export function setActivityRefresher(value: (() => Promise<void>) | null) {
  refresher = value;
}
/** Concurrent sockets share one re-handshake; resolves false if it failed. */
export function refreshActivityCredential(): Promise<boolean> {
  if (!refresher) return Promise.resolve(false);
  refreshing ??= refresher()
    .then(
      () => true,
      () => false,
    )
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}
export function getActivityUser(): UserType | undefined {
  return session?.user;
}
export function activityAuthorization(path: string): string | undefined {
  if (!session) return;
  const draftPath =
    session.kind === 'hero'
      ? `/herodraft/${session.draft_id}/`
      : `/draft/${session.draft_id}/`;
  if (
    path.startsWith(draftPath) ||
    path === '/current_user' ||
    (session.kind === 'team' &&
      [
        '/tournaments/pick_player',
        '/tournaments/undo-pick',
        '/draft/get-style-mmrs',
      ].includes(path))
  ) {
    return `DraftActivity ${session.token}`;
  }
}
export function activitySocket(kind: 'hero' | 'team', id: number) {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const active = session?.kind === kind && session.draft_id === id;
  const path = active
    ? `/api/discord/activity/${kind === 'hero' ? 'draft' : 'team-draft'}/${id}/`
    : `/api/${kind === 'hero' ? 'herodraft' : 'draft'}/${id}/`;
  return {
    url: `${protocol}//${window.location.host}${path}`,
    protocols: active ? ['draftactivity', session!.token] : undefined,
  };
}
