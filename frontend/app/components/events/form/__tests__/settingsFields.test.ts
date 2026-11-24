import { describe, expect, it } from 'vitest';
import { DraftSettingsFormSchema } from '~/components/teamdraft/schemas';
import {
  createEventInputSchema,
  createSeriesEventInputSchema,
  dotaLobbyConfigSchema,
  editEventFormSchema,
  readyCheckConfigSchema,
} from '../../schemas';
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

  it('covers every ready check field under Ready check', () => {
    expect(Object.keys(EVENT_SECTION_FIELDS.ready).sort()).toEqual(
      Object.keys(readyCheckConfigSchema.shape).sort(),
    );
  });

  it('only lists fields an event form actually has', () => {
    const formFields = new Set([
      ...Object.keys(createEventInputSchema.shape),
      ...Object.keys(createSeriesEventInputSchema.shape),
      ...Object.keys(editEventFormSchema.shape),
      // useOrgEventDefaultsSections keeps these in its own local schema.
      'max_players',
      'auto_approve',
    ]);
    const stale = Object.values(EVENT_SECTION_FIELDS)
      .flatMap(Object.keys)
      .filter((field) => !formFields.has(field));
    expect(stale).toEqual([]);
  });

  it('describes the Friend ID requirement without naming one game', () => {
    expect(
      EVENT_SECTION_FIELDS.approval.require_steam_id.description,
    ).not.toMatch(/dota/i);
  });
});

describe('discord_signup_reminder metadata', () => {
  const meta = EVENT_SECTION_FIELDS.discord.discord_signup_reminder;
  it('names series subscribers as recipients', () => {
    expect(meta.description).toBe(
      "DM series subscribers who haven't signed up yet, before the event starts",
    );
    expect(meta.description).not.toMatch(/\bDM users\b/i);
  });
});
