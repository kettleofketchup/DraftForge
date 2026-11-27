import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { DISCORD_CONFIG_DEFAULTS } from '~/components/events/schemas';
import { settingsDescriptors } from '../descriptors';

const cases: {
  name: string;
  settings: Partial<typeof DISCORD_CONFIG_DEFAULTS>;
  expected: Record<string, { channel_id: string | null } | null>;
}[] = JSON.parse(
  readFileSync(
    new URL(
      '../../../../../backend/events/tests/permission_destination_cases.json',
      import.meta.url,
    ),
    'utf8',
  ),
);

describe('settingsDescriptors', () => {
  it.each(cases)(
    'matches saved destination contract: $name',
    ({ settings, expected }) => {
      const descriptors = settingsDescriptors(
        { ...DISCORD_CONFIG_DEFAULTS, ...settings },
        { isRepeater: true, showNotifyNewEvents: true },
      );
      for (const [key, destination] of Object.entries(expected)) {
        const descriptor = descriptors.find((d) => d.key === key);
        if (destination === null && key === 'announcement')
          expect(descriptor?.channel_id).toBe(
            settings.discord_announcement_channel_id || null,
          );
        else if (destination === null) expect(descriptor).toBeUndefined();
        else
          expect(descriptor?.channel_id).toBe(
            (destination as { channel_id: string | null }).channel_id,
          );
      }
    },
  );

  it('omits hidden nested and series controls', () => {
    const descriptors = settingsDescriptors(
      {
        ...DISCORD_CONFIG_DEFAULTS,
        discord_sync_signups: true,
        discord_mark_interested: true,
        discord_notify_new_events: true,
      },
      { isRepeater: false, showNotifyNewEvents: false },
    );
    for (const key of [
      'scheduled_event_update',
      'mark_interested',
      'new_event_notice',
      'signup_reminder',
    ]) {
      expect(descriptors.some((d) => d.key === key)).toBe(false);
    }
    expect(descriptors.some((d) => d.key === 'scheduled_event_create')).toBe(
      true,
    );
  });

  it.each([
    { isRepeater: false, showSignupReminder: true, visible: true },
    { isRepeater: true, showSignupReminder: false, visible: false },
  ])('follows explicit reminder visibility: $showSignupReminder', (opts) => {
    const descriptors = settingsDescriptors(DISCORD_CONFIG_DEFAULTS, {
      ...opts,
      showNotifyNewEvents: false,
    });
    expect(descriptors.some((d) => d.key === 'signup_reminder')).toBe(
      opts.visible,
    );
  });

  it('marks only inherited channels as fallback destinations', () => {
    const announcement = '900000000000000003';
    const own = '900000000000000007';
    const descriptors = settingsDescriptors(
      {
        ...DISCORD_CONFIG_DEFAULTS,
        discord_announcement: true,
        discord_announcement_channel_id: announcement,
        discord_post_signups: true,
        discord_confirm_attendance: true,
        discord_confirm_attendance_channel_id: own,
        discord_profile_reminder: true,
        discord_profile_reminder_channel_id: '',
      },
      { isRepeater: false, showNotifyNewEvents: false },
    );
    const byKey = Object.fromEntries(descriptors.map((d) => [d.key, d]));
    expect(byKey.attendance_reminder).toMatchObject({
      channel_id: own,
      fallback: false,
    });
    expect(byKey.profile_reminder).toMatchObject({
      channel_id: announcement,
      fallback: true,
    });
    expect(byKey.signup_fallback.fallback).toBe(true);
    expect(byKey.announcement.fallback).toBe(true);
  });

  it.each([
    {
      discord_post_signups: false,
      discord_post_signups_channel_id: '',
      roles: [],
    },
    {
      discord_post_signups: true,
      discord_post_signups_channel_id: '',
      roles: [],
    },
    {
      discord_post_signups: true,
      discord_post_signups_channel_id: '900000000000000007',
      roles: ['900000000000000005'],
    },
  ])(
    'checks announcement roles only when the notice is sent: $discord_post_signups $discord_post_signups_channel_id',
    ({ roles, ...settings }) => {
      const descriptors = settingsDescriptors(
        {
          ...DISCORD_CONFIG_DEFAULTS,
          ...settings,
          discord_announcement: true,
          discord_announcement_channel_id: '900000000000000003',
          discord_announcement_role_ids: ['900000000000000005'],
        },
        { isRepeater: false, showNotifyNewEvents: false },
      );
      expect(descriptors.find((d) => d.key === 'announcement')).toMatchObject({
        action: roles.length ? 'announcement' : 'signup_fallback',
        channel_id: '900000000000000003',
        role_ids: roles,
      });
    },
  );

  it('uses separate fallback transport and prospective start destination', () => {
    const descriptors = settingsDescriptors(
      {
        ...DISCORD_CONFIG_DEFAULTS,
        discord_post_signups: true,
        discord_start_mention: true,
        discord_announcement: true,
        discord_announcement_channel_id: '900000000000000003',
      },
      { isRepeater: false, showNotifyNewEvents: false },
    );
    expect(descriptors.find((d) => d.key === 'signup_fallback')).toMatchObject({
      action: 'signup_fallback',
      channel_id: '900000000000000003',
    });
    expect(descriptors.find((d) => d.key === 'start_mention')?.channel_id).toBe(
      '900000000000000003',
    );
    expect(descriptors.find((d) => d.key === 'signup_post')).toBeUndefined();
  });
});
