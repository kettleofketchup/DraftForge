/** Activity credentials stay in memory and are never sent to unrelated APIs. */
export interface ActivityCredential {
  token: string;
  draft_id: number;
  kind: 'hero' | 'team';
}
let session: ActivityCredential | null = null;
export function setActivityCredential(value: ActivityCredential | null) {
  session = value;
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
    (session.kind === 'team' && path === '/tournaments/pick_player')
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
