import { describe, expect, it } from 'vitest';
import { DraftSettingsFormSchema } from '~/components/teamdraft/schemas';
import {
  createEventInputSchema,
  createSeriesEventInputSchema,
  dotaLobbyConfigSchema,
  editEventFormSchema,
  readyCheckConfigSchema,
} from '../../schemas';
import {
  EVENT_SECTION_FIELDS,
  PROFILE_REMINDER_DESCRIPTION,
} from '../settingsFields';
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

  it('lists the staff reason policy under Approval with search keywords', () => {
    const entry = EVENT_SECTION_FIELDS.approval.staff_reason_policy;
    expect(entry.label).toBe('Staff reasons');
    expect(entry.keywords).toEqual(
      expect.arrayContaining(['reason', 'audit', 'staff', 'placement']),
    );
  });

  it('describes the Friend ID requirement without naming one game', () => {
    expect(
      EVENT_SECTION_FIELDS.approval.require_steam_id.description,
    ).not.toMatch(/dota/i);
  });
});

describe('discord_profile_reminder copy', () => {
  const entry = EVENT_SECTION_FIELDS.discord.discord_profile_reminder;
  it('uses the shared description', () => {
    expect(entry.description).toBe(PROFILE_REMINDER_DESCRIPTION);
  });
  it('describes an announcement-channel post, not a DM', () => {
    expect(PROFILE_REMINDER_DESCRIPTION).toMatch(/announcement channel/i);
    expect(PROFILE_REMINDER_DESCRIPTION).not.toMatch(/\bDM/);
    expect(PROFILE_REMINDER_DESCRIPTION).not.toMatch(/dota/i);
    expect(PROFILE_REMINDER_DESCRIPTION).not.toMatch(/mmr/i);
    expect(PROFILE_REMINDER_DESCRIPTION).not.toMatch(/mention|ping/i);
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
