import { describe, expect, it } from 'vitest';

import { fallbackChannelUsers } from '../fallbackChannelUsers';
import { EVENT_SECTION_FIELDS } from '../form/settingsFields';

const label = (field: string): string =>
  EVENT_SECTION_FIELDS.discord[field].label;

describe('fallbackChannelUsers', () => {
  it('is empty when nothing is on', () => {
    expect(fallbackChannelUsers({ showNotifyNewEvents: true })).toEqual([]);
  });

  it('lists the announcement and each blank-own post that is on', () => {
    expect(
      fallbackChannelUsers({
        announcement: true,
        postSignups: true,
        confirmAttendance: true,
        profileReminder: true,
        notifyNewEvents: true,
        showNotifyNewEvents: true,
      }),
    ).toEqual([
      label('discord_announcement'),
      label('discord_post_signups'),
      label('discord_confirm_attendance'),
      label('discord_profile_reminder'),
      label('discord_notify_new_events'),
    ]);
  });

  it('excludes posts with their own channel', () => {
    expect(
      fallbackChannelUsers({
        announcement: true,
        postSignups: true,
        signupChannelId: '1',
        confirmAttendance: true,
        attendanceChannelId: '2',
        profileReminder: true,
        profileChannelId: '3',
        notifyNewEvents: true,
        newEventChannelId: '4',
        showNotifyNewEvents: true,
      }),
    ).toEqual([label('discord_announcement')]);
  });

  it('includes a blank-own post next to one with its own channel', () => {
    expect(
      fallbackChannelUsers({
        confirmAttendance: true,
        attendanceChannelId: '2',
        profileReminder: true,
        profileChannelId: '',
        showNotifyNewEvents: false,
      }),
    ).toEqual([label('discord_profile_reminder')]);
  });

  it('excludes new events when the toggle is not shown', () => {
    expect(
      fallbackChannelUsers({
        notifyNewEvents: true,
        showNotifyNewEvents: false,
      }),
    ).toEqual([]);
  });

  it('excludes the signup post while the announcement is off', () => {
    expect(
      fallbackChannelUsers({
        announcement: false,
        postSignups: true,
        showNotifyNewEvents: false,
      }),
    ).toEqual([]);
  });
});
