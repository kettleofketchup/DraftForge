import { describe, expect, it } from 'vitest';
import { DraftSettingsFormSchema } from '~/components/teamdraft/schemas';
import { dotaLobbyConfigSchema } from '../../schemas';
import { EVENT_SECTION_FIELDS } from '../settingsFields';
import { EVENT_TAB_META } from '../tabs';

describe('EVENT_SECTION_FIELDS', () => {
  it('has an entry for every section', () => {
    expect(Object.keys(EVENT_SECTION_FIELDS).sort()).toEqual(
      Object.keys(EVENT_TAB_META).sort(),
    );
  });

  it('lists each field under one section only', () => {
    const all = Object.values(EVENT_SECTION_FIELDS).flatMap(Object.keys);
    expect(all.length).toBe(new Set(all).size);
  });

  it('covers every draft settings field under Tournament', () => {
    for (const key of Object.keys(DraftSettingsFormSchema.shape)) {
      expect(EVENT_SECTION_FIELDS.tournament).toHaveProperty(key);
    }
  });

  it('covers every hosted lobby field under Lobby', () => {
    for (const key of Object.keys(dotaLobbyConfigSchema.shape)) {
      expect(EVENT_SECTION_FIELDS.lobby).toHaveProperty(key);
    }
  });
});
