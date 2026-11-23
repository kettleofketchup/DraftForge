import { safeTimeZone } from '~/features/standing/periods';
import type { ReleaseState } from './schemas';

export type ReleaseBadgeTone =
  | 'default'
  | 'secondary'
  | 'destructive'
  | 'outline';

export type ReleaseBadge = { label: string; tone: ReleaseBadgeTone };

export const RELEASE_BADGES: Record<ReleaseState, ReleaseBadge> = {
  released: { label: 'Released', tone: 'secondary' },
  pending: { label: 'Pending release', tone: 'default' },
  open: { label: 'Window open', tone: 'outline' },
  short: { label: 'Not enough reviews', tone: 'outline' },
  voided: { label: 'Voided', tone: 'destructive' },
  hidden: { label: 'Hidden', tone: 'outline' },
};

export function releaseBadge(state: ReleaseState): ReleaseBadge {
  return RELEASE_BADGES[state];
}

export function formatReleaseTime(iso: string): string {
  return new Intl.DateTimeFormat('en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: safeTimeZone(undefined),
  }).format(new Date(iso));
}
