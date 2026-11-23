import { Award, ShieldCheck } from 'lucide-react';
import { describe, expect, it, vi } from 'vitest';
import type { TrackInfo, TrackKey } from '../schemas';
import { isStandingTabValue, visibleStandingTabs } from '../visibleTracks';

vi.mock('../panels', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../panels')>();
  const base = {
    sampleLabel: () => null,
    totalUnit: null,
    emptyLabel: () => '',
    canOpen: () => true,
    openOwnByDefault: false,
    Detail: () => null,
  };
  const panels = {
    contribution: { ...base, tabValue: 'contributions', icon: Award },
    conduct: { ...base, tabValue: 'conduct', icon: ShieldCheck },
    leadership: actual.TRACK_PANELS.leadership,
  };
  return {
    TRACK_PANELS: panels,
    panelFor: (key: TrackKey) => panels[key as keyof typeof panels],
  };
});

const track = (key: TrackKey, over: Partial<TrackInfo> = {}): TrackInfo => ({
  key,
  label:
    key === 'contribution'
      ? 'Contributions'
      : key[0].toUpperCase() + key.slice(1),
  metrics: [
    { key: 'm', label: 'M', format: 'int', periodic: false, default: true },
  ],
  can_view_rows: true,
  can_view_own: true,
  board_open: true,
  can_manage: false,
  ...over,
});

describe('visibleStandingTabs', () => {
  it('lists contribution and conduct in backend order', () => {
    const tabs = visibleStandingTabs([track('contribution'), track('conduct')]);
    expect(tabs.map((t) => t.value)).toEqual(['contributions', 'conduct']);
    expect(tabs.map((t) => t.label)).toEqual(['Contributions', 'Conduct']);
    expect(tabs[1].icon).toBe(ShieldCheck);
    expect(tabs[1].track.key).toBe('conduct');
  });

  it('keeps a closed board the viewer can see their own row on', () => {
    const tabs = visibleStandingTabs([
      track('conduct', { board_open: false, can_view_own: true }),
    ]);
    expect(tabs.map((t) => t.value)).toEqual(['conduct']);
  });

  it('hides a closed board with no own row', () => {
    expect(
      visibleStandingTabs([
        track('conduct', { board_open: false, can_view_own: false }),
      ]),
    ).toEqual([]);
  });

  it('drops tracks without a panel set', () => {
    expect(
      visibleStandingTabs([
        track('unregistered' as TrackKey),
        track('contribution'),
      ]).map((t) => t.value),
    ).toEqual(['contributions']);
  });

  it('registers the leadership tab', () => {
    const tabs = visibleStandingTabs([track('leadership')]);
    expect(tabs.map((t) => ({ value: t.value, label: t.label }))).toEqual([
      { value: 'leadership', label: 'Leadership' },
    ]);
  });
});

describe('isStandingTabValue', () => {
  it('is true for every registered track tab', () => {
    expect(isStandingTabValue('conduct')).toBe(true);
    expect(isStandingTabValue('contributions')).toBe(true);
    expect(isStandingTabValue('leadership')).toBe(true);
  });

  it('is false for other tabs', () => {
    expect(isStandingTabValue('leagues')).toBe(false);
  });
});
