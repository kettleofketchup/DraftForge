import { describe, expect, it } from 'vitest';
import {
  DEFAULT_EVENT_TAB,
  canViewEventTab,
  visibleEventTab,
} from '~/components/events/eventTabs';

describe('event tab visibility', () => {
  it('shows the Discord tab only to event staff', () => {
    expect(canViewEventTab('discord', true)).toBe(true);
    expect(canViewEventTab('discord', false)).toBe(false);
  });

  it('sends a non-staff visit to the Discord tab URL to the details tab', () => {
    expect(visibleEventTab('discord', false)).toBe(DEFAULT_EVENT_TAB);
    expect(DEFAULT_EVENT_TAB).toBe('details');
  });

  it('keeps staff on the Discord tab', () => {
    expect(visibleEventTab('discord', true)).toBe('discord');
  });

  it.each(['details', 'signups', 'tentative', 'waitlist', 'removed'])(
    'leaves the public %s tab alone for everyone',
    (tab) => {
      expect(visibleEventTab(tab, false)).toBe(tab);
      expect(visibleEventTab(tab, true)).toBe(tab);
    },
  );
});
