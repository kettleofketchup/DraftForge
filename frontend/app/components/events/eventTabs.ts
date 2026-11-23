export type EventTabCounts = {
  active: number;
  tentative: number;
  waitlisted: number;
  removed: number;
};

export type EventTabOption = { value: string; label: string };

const STAFF_TABS = new Set(['history']);

/** Phone page-nav options for the event page; History is staff-only. */
export function eventTabOptions(
  isAdmin: boolean,
  counts: EventTabCounts,
): EventTabOption[] {
  return [
    { value: 'details', label: 'Details' },
    { value: 'signups', label: `${counts.active} Signups` },
    ...(counts.tentative > 0
      ? [{ value: 'tentative', label: `${counts.tentative} Tentative` }]
      : []),
    { value: 'waitlist', label: `${counts.waitlisted} Waitlist` },
    ...(counts.removed > 0
      ? [{ value: 'removed', label: `${counts.removed} Removed` }]
      : []),
    { value: 'discord', label: 'Discord' },
    ...(isAdmin ? [{ value: 'history', label: 'History' }] : []),
  ];
}

/** Falls back to Details when a non-staff viewer lands on a staff-only tab. */
export function resolveEventTab(tab: string, isAdmin: boolean): string {
  return !isAdmin && STAFF_TABS.has(tab) ? 'details' : tab;
}
