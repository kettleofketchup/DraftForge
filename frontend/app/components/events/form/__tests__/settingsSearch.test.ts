// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import type { SectionFieldMeta } from '../settingsFields';
import {
  buildSettingsIndex,
  resolveFieldSection,
  scanFieldPlacements,
  searchSettings,
  sectionsWithErrors,
  type FieldPlacements,
} from '../settingsSearch';

const meta: SectionFieldMeta = {
  event: {
    name: { label: 'Event Name' },
    timezone: { label: 'Timezone', keywords: ['tz', 'utc'] },
  },
  tournament: {
    people_per_team: { label: 'People Per Team', keywords: ['team size'] },
    draft_grace_time_s: {
      label: 'Grace time (seconds)',
      description: 'Resets every pick',
    },
  },
  lobby: { game_mode: { label: 'Game Mode' } },
  approval: {
    min_mmr: { label: 'Minimum MMR', description: 'Lowest MMR allowed' },
    roll_call_enabled: { label: 'Roll call' },
  },
  discord: {
    discord_announcement: {
      label: 'Pre-day announcement',
      description: 'Post an announcement in a channel before the event',
    },
  },
};

const placed = (
  entries: Record<string, string | { section: string; label?: string }>,
): FieldPlacements =>
  new Map(
    Object.entries(entries).map(([field, v]) => [
      field,
      typeof v === 'string' ? { section: v } : v,
    ]),
  ) as FieldPlacements;

describe('scanFieldPlacements', () => {
  it('maps each data-field to its data-section with the rendered label', () => {
    document.body.innerHTML = `
      <div data-section="event">
        <div data-field="name"><label>Event Name</label>
          <p id="x-form-item-description">Shown on the card</p></div>
      </div>
      <div data-section="approval" hidden>
        <div data-field="roll_call_enabled"><label>Roll call</label></div>
        <div data-field="roll_call_enabled"><label>Duplicate</label></div>
      </div>
      <div data-field="orphan"></div>`;
    const map = scanFieldPlacements(document.body);
    expect(map.get('name')).toEqual({
      section: 'event',
      label: 'Event Name',
      description: 'Shown on the card',
    });
    expect(map.get('roll_call_enabled')?.label).toBe('Roll call');
    expect(map.has('orphan')).toBe(false);
  });
});

describe('buildSettingsIndex', () => {
  it('keeps fields rendered in the modal at the section they render in', () => {
    const index = buildSettingsIndex({
      sections: [
        { value: 'event', mounted: true },
        { value: 'approval', mounted: true },
      ],
      placements: placed({ name: 'event', roll_call_enabled: 'event' }),
      meta,
    });
    expect(index.map((e) => [e.field, e.section])).toEqual([
      ['name', 'event'],
      ['roll_call_enabled', 'event'],
    ]);
  });

  it('includes every registry field of a lazy section that is not mounted yet', () => {
    const index = buildSettingsIndex({
      sections: [
        { value: 'event', mounted: true },
        { value: 'discord', mounted: false },
      ],
      placements: placed({ name: 'event' }),
      meta,
    });
    expect(index.map((e) => e.field)).toEqual(['name', 'discord_announcement']);
  });

  it('drops registry fields of sections the modal does not have', () => {
    const index = buildSettingsIndex({
      sections: [{ value: 'event', mounted: true }],
      placements: placed({ name: 'event' }),
      meta,
    });
    expect(index.some((e) => e.section === 'approval')).toBe(false);
  });

  it('prefers the rendered label and indexes unregistered rendered fields', () => {
    const index = buildSettingsIndex({
      sections: [{ value: 'tournament', mounted: true }],
      placements: placed({
        people_per_team: { section: 'tournament', label: 'Team size' },
        brand_new_field: { section: 'tournament', label: 'Brand new' },
      }),
      meta,
    });
    expect(index).toEqual([
      expect.objectContaining({
        field: 'people_per_team',
        label: 'Team size',
        keywords: ['team size'],
      }),
      expect.objectContaining({ field: 'brand_new_field', label: 'Brand new' }),
    ]);
  });
});

describe('searchSettings', () => {
  const index = buildSettingsIndex({
    sections: [
      { value: 'event', mounted: true },
      { value: 'tournament', mounted: true },
      { value: 'approval', mounted: true },
      { value: 'discord', mounted: false },
    ],
    placements: placed({
      name: 'event',
      timezone: 'event',
      people_per_team: 'tournament',
      draft_grace_time_s: 'tournament',
      min_mmr: 'approval',
    }),
    meta,
  });
  const order = ['event', 'tournament', 'approval', 'discord'] as const;

  const hits = (q: string) =>
    searchSettings(index, [...order], q).flatMap((g) =>
      g.entries.map((e) => e.field),
    );

  it('returns no groups for a blank query', () => {
    expect(searchSettings(index, [...order], '   ')).toEqual([]);
  });

  it('matches labels case-insensitively', () => {
    expect(hits('mmr')).toEqual(['min_mmr']);
  });

  it('matches descriptions and keywords', () => {
    expect(hits('every pick')).toEqual(['draft_grace_time_s']);
    expect(hits('UTC')).toEqual(['timezone']);
  });

  it('requires every token to match', () => {
    expect(hits('announcement channel')).toEqual(['discord_announcement']);
    expect(hits('announcement mmr')).toEqual([]);
  });

  it('groups by section in section order, keeping empty sections', () => {
    const groups = searchSettings(index, [...order], 'e');
    expect(groups.map((g) => g.section)).toEqual([...order]);
    expect(searchSettings(index, [...order], 'mmr')).toEqual([
      { section: 'event', entries: [] },
      { section: 'tournament', entries: [] },
      {
        section: 'approval',
        entries: [expect.objectContaining({ field: 'min_mmr' })],
      },
      { section: 'discord', entries: [] },
    ]);
  });

  it('ranks label prefix matches before other matches', () => {
    const local = buildSettingsIndex({
      sections: [{ value: 'event', mounted: true }],
      placements: placed({
        a: { section: 'event', label: 'Max players' },
        b: { section: 'event', label: 'Players per team' },
      }),
      meta: { event: {}, tournament: {}, lobby: {}, approval: {}, discord: {} },
    });
    expect(
      searchSettings(local, ['event'], 'play')[0].entries.map((e) => e.field),
    ).toEqual(['b', 'a']);
  });
});

describe('resolveFieldSection', () => {
  it('uses where the field renders, then the registry, then the first section', () => {
    const p = placed({ roll_call_enabled: 'event' });
    const available = ['event', 'tournament', 'approval'] as const;
    expect(resolveFieldSection('roll_call_enabled', p, [...available])).toBe(
      'event',
    );
    expect(resolveFieldSection('min_mmr', p, [...available])).toBe('approval');
    expect(
      resolveFieldSection('discord_event_title', p, ['event', 'lobby']),
    ).toBe('event');
  });
});

describe('sectionsWithErrors', () => {
  it('collects the section of every errored field, ignoring root errors', () => {
    const p = placed({ name: 'event' });
    expect(
      sectionsWithErrors(['name', 'people_per_team', 'root'], p, [
        'event',
        'tournament',
        'discord',
      ]),
    ).toEqual(new Set(['event', 'tournament']));
  });
});
