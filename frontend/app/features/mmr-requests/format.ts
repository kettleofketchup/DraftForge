import { format } from 'date-fns';
import { GAME_LABEL, toGameType } from '~/components/game/constants';
import type { MmrChangeRequest } from './schemas';

export function formatMmrDate(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? null : format(date, 'd MMM yyyy');
}

export function requestTargetLabel(request: MmrChangeRequest): string {
  return request.target === 'org'
    ? `Org MMR · ${GAME_LABEL[toGameType(request.game_type)]}`
    : `League · ${request.league?.name ?? 'Unknown league'}`;
}
