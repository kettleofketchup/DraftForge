export const DEFAULT_EVENT_TAB = 'details';

const STAFF_ONLY_EVENT_TABS: ReadonlySet<string> = new Set(['discord']);

export function canViewEventTab(tab: string, isStaff: boolean): boolean {
  return isStaff || !STAFF_ONLY_EVENT_TABS.has(tab);
}

export function visibleEventTab(tab: string, isStaff: boolean): string {
  return canViewEventTab(tab, isStaff) ? tab : DEFAULT_EVENT_TAB;
}
