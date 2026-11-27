import { differenceInDays, format } from 'date-fns';
import { GAME_LABEL, toGameType } from '~/components/game/constants';
import type { MmrChangeRequest } from './schemas';

export function formatMmrDate(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? null : format(date, 'd MMM yyyy');
}

export function withPendingCount(label: string, count: number): string {
  return count > 0 ? `${label} (${count})` : label;
}

export function requestTargetLabel(request: MmrChangeRequest): string {
  return request.target === 'org'
    ? `Org MMR · ${GAME_LABEL[toGameType(request.game_type)]}`
    : `League · ${request.league?.name ?? 'Unknown league'}`;
}

export function screenshotRemovedLabel(request: MmrChangeRequest): string {
  if (!request.reviewed_at || !request.screenshot_purged_at) {
    return 'Screenshot removed';
  }
  const days = differenceInDays(
    new Date(request.screenshot_purged_at),
    new Date(request.reviewed_at),
  );
  if (Number.isNaN(days)) return 'Screenshot removed';
  return `Screenshot removed after ${days} ${days === 1 ? 'day' : 'days'}`;
}
