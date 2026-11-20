import type { ChatMessage, ChatViewer, DraftTeam } from '../types';

export const PREVIEW_MAX_LINES = 2;
export const PREVIEW_TTL_MS = 4500;
export const PREVIEW_FADE_MS = 500;

export interface PreviewLine {
  key: string;
  message: ChatMessage;
  count: number;
  expiresAt: number;
}

export interface PreviewContext {
  viewer: ChatViewer | null;
  selfId?: number;
  /** Captain and member pks of the viewer's team; null when not derivable. */
  roster: ReadonlySet<number> | null;
}

export function teamRoster(
  teams:
    | Pick<DraftTeam, 'tournament_team' | 'captain' | 'members'>[]
    | undefined,
  teamId: number | null | undefined,
): Set<number> | null {
  if (teamId == null) return null;
  const team = teams?.find((t) => t.tournament_team === teamId);
  if (!team) return null;
  const pks = new Set(team.members.map((m) => m.pk));
  if (team.captain) pks.add(team.captain.pk);
  return pks;
}

export function shouldPreview(m: ChatMessage, ctx: PreviewContext): boolean {
  if (ctx.selfId !== undefined && m.sender.pk === ctx.selfId) {
    return m.kind !== 'text';
  }
  if (ctx.viewer?.role !== 'member') return true;
  if (m.channel === 'team') return true;
  return ctx.roster?.has(m.sender.pk) ?? false;
}

export function expirePreview(
  lines: PreviewLine[],
  now: number,
): PreviewLine[] {
  const live = lines.filter((l) => l.expiresAt > now);
  return live.length === lines.length ? lines : live;
}

export function pushPreview(
  lines: PreviewLine[],
  m: ChatMessage,
  now: number,
): PreviewLine[] {
  const live = expirePreview(lines, now);
  const last = live.at(-1);
  const expiresAt = now + PREVIEW_TTL_MS;
  if (last && last.message.sender.pk === m.sender.pk) {
    return [
      ...live.slice(0, -1),
      { ...last, message: m, count: last.count + 1, expiresAt },
    ];
  }
  return [...live, { key: m.id, message: m, count: 1, expiresAt }].slice(
    -PREVIEW_MAX_LINES,
  );
}

/** Next time a line starts fading or expires, or null when nothing is pending. */
export function nextPreviewBoundary(
  lines: PreviewLine[],
  now: number,
): number | null {
  let next: number | null = null;
  for (const l of lines) {
    for (const t of [l.expiresAt - PREVIEW_FADE_MS, l.expiresAt]) {
      if (t > now && (next === null || t < next)) next = t;
    }
  }
  return next;
}
