import { describe, expect, it } from 'vitest';

import { eventTabOptions, resolveEventTab } from '../eventTabs';

const COUNTS = { active: 3, tentative: 0, waitlisted: 1, removed: 2 };

describe('eventTabOptions', () => {
  it('adds History after Discord for staff', () => {
    expect(eventTabOptions(true, COUNTS)).toEqual([
      { value: 'details', label: 'Details' },
      { value: 'signups', label: '3 Signups' },
      { value: 'waitlist', label: '1 Waitlist' },
      { value: 'removed', label: '2 Removed' },
      { value: 'discord', label: 'Discord' },
      { value: 'history', label: 'History' },
    ]);
  });

  it('never offers Discord or History to members', () => {
    const values = eventTabOptions(false, COUNTS).map((o) => o.value);
    expect(values).not.toContain('history');
    expect(values).not.toContain('discord');
  });

  it('shows Tentative and Removed only when they have rows', () => {
    const values = eventTabOptions(false, {
      active: 0,
      tentative: 2,
      waitlisted: 0,
      removed: 0,
    }).map((o) => o.value);
    expect(values).toEqual(['details', 'signups', 'tentative', 'waitlist']);
  });
});

describe('resolveEventTab', () => {
  it('sends non-staff on the history tab to details', () => {
    expect(resolveEventTab('history', false)).toBe('details');
  });

  it('sends non-staff on the Discord tab to details', () => {
    expect(resolveEventTab('discord', false)).toBe('details');
  });

  it('keeps history for staff', () => {
    expect(resolveEventTab('history', true)).toBe('history');
  });

  it('leaves other tabs alone', () => {
    for (const tab of [
      'details',
      'signups',
      'tentative',
      'waitlist',
      'removed',
    ]) {
      expect(resolveEventTab(tab, false)).toBe(tab);
      expect(resolveEventTab(tab, true)).toBe(tab);
    }
    expect(resolveEventTab('discord', true)).toBe('discord');
  });
});
