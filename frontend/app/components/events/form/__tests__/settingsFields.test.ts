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
  ATTENDANCE_REMINDER_DESCRIPTION,
  EVENT_SECTION_FIELDS,
  NEW_EVENTS_DESCRIPTION,
  PROFILE_REMINDER_DESCRIPTION,
  SIGNUP_REMINDER_LABEL,
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

  it('describes the Friend ID requirement without naming one game', () => {
    expect(
      EVENT_SECTION_FIELDS.approval.require_steam_id.description,
    ).not.toMatch(/dota/i);
  });
});

describe('per-post channel fields', () => {
  const discord = EVENT_SECTION_FIELDS.discord;
  it('lists the per-post channel fields under Discord', () => {
    expect(discord.discord_confirm_attendance_channel_id?.label).toBe(
      'Attendance reminder channel',
    );
    expect(discord.discord_profile_reminder_channel_id?.label).toBe(
      'Profile reminder channel',
    );
    expect(discord.discord_new_event_channel_id?.label).toBe(
      'New event channel',
    );
    for (const key of [
      'discord_confirm_attendance_channel_id',
      'discord_profile_reminder_channel_id',
      'discord_new_event_channel_id',
    ]) {
      expect(discord[key]?.keywords).toEqual(
        expect.arrayContaining(['channel', 'post']),
      );
      expect(discord[key]?.description).toMatch(/announcement channel/i);
      expect(discord[key]?.description).toMatch(/blank/i);
    }
  });

  it('describes channel posts by their own channel', () => {
    expect(discord.discord_confirm_attendance?.description).toBe(
      ATTENDANCE_REMINDER_DESCRIPTION,
    );
    expect(discord.discord_notify_new_events?.description).toBe(
      NEW_EVENTS_DESCRIPTION,
    );
    expect(discord.discord_profile_reminder?.description).toBe(
      PROFILE_REMINDER_DESCRIPTION,
    );
    for (const text of [
      ATTENDANCE_REMINDER_DESCRIPTION,
      NEW_EVENTS_DESCRIPTION,
      PROFILE_REMINDER_DESCRIPTION,
    ]) {
      expect(text).toMatch(/in its channel/);
      expect(text).toMatch(/when none is picked/);
      expect(text).not.toMatch(/in the announcement channel/);
    }
  });

  it('describes the announcement channel as the fallback', () => {
    expect(discord.discord_announcement_channel_id?.description).toBe(
      'Channel for the pre-day announcement, and for reminders and new-event posts that have no channel of their own.',
    );
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

  it('signup reminder label matches the rendered toggle', () => {
    expect(SIGNUP_REMINDER_LABEL).toBe('Signup reminder DM');
    expect(meta.label).toBe(SIGNUP_REMINDER_LABEL);
    expect(meta.keywords).toEqual(
      expect.arrayContaining(['dm', 'direct message', 'subscribers']),
    );
  });

  it('stays listed under the Discord section exactly once', () => {
    const sections = Object.entries(EVENT_SECTION_FIELDS)
      .filter(([, fields]) => 'discord_signup_reminder' in fields)
      .map(([section]) => section);
    expect(sections).toEqual(['discord']);
  });
});
