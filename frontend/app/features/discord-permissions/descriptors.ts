import type { DiscordFields } from '~/components/events/DiscordConfigSection';
import type { ActionKind, CheckDescriptor } from './schemas';

export const SETTINGS_OPERATIONS: Record<
  string,
  { field: keyof DiscordFields; label: string }
> = {
  signup_post: { field: 'discord_post_signups', label: 'Signup post' },
  signup_fallback: {
    field: 'discord_post_signups',
    label: 'Signup announcement fallback',
  },
  announcement: { field: 'discord_announcement', label: 'Announcement' },
  attendance_reminder: {
    field: 'discord_confirm_attendance',
    label: 'Attendance reminder',
  },
  profile_reminder: {
    field: 'discord_profile_reminder',
    label: 'Profile reminder',
  },
  new_event_notice: {
    field: 'discord_notify_new_events',
    label: 'New event notice',
  },
  start_mention: { field: 'discord_start_mention', label: 'Start mention' },
  scheduled_event_create: {
    field: 'discord_create_event',
    label: 'Create scheduled event',
  },
  scheduled_event_update: {
    field: 'discord_sync_signups',
    label: 'Synchronize signups',
  },
  mark_interested: {
    field: 'discord_mark_interested',
    label: 'Mark interested',
  },
  signup_reminder: {
    field: 'discord_signup_reminder',
    label: 'Signup reminder DM',
  },
};

export function settingsDescriptors(
  values: DiscordFields,
  opts: {
    isRepeater: boolean;
    showNotifyNewEvents: boolean;
    showSignupReminder?: boolean;
  },
): CheckDescriptor[] {
  const checks: CheckDescriptor[] = [];
  const announcement = values.discord_announcement_channel_id || null;
  const signup = values.discord_post_signups_channel_id || null;
  const fallback = values.discord_announcement ? announcement : null;
  const add = (
    key: string,
    action: ActionKind,
    channel_id: string | null = null,
    role_ids: string[] = [],
    fallback = false,
  ) => {
    checks.push({
      key,
      action,
      channel_id,
      role_ids,
      include_rsvp: false,
      fallback,
    });
  };
  const own = (channel: string): [string | null, string[], boolean] => [
    channel || announcement,
    [],
    !channel && !!announcement,
  ];
  add('scheduled_event_create', 'scheduled_event_create');
  if (values.discord_create_event) {
    add('scheduled_event_update', 'scheduled_event_update');
    add('mark_interested', 'mark_interested');
  }
  if (signup || !fallback)
    add('signup_post', 'signup_create', signup, values.discord_signup_role_ids);
  if (fallback) add('signup_fallback', 'signup_fallback', fallback, [], true);
  add(
    'announcement',
    'announcement',
    announcement,
    values.discord_announcement_role_ids,
  );
  add(
    'attendance_reminder',
    'attendance_reminder',
    ...own(values.discord_confirm_attendance_channel_id),
  );
  add(
    'profile_reminder',
    'profile_reminder',
    ...own(values.discord_profile_reminder_channel_id),
  );
  if (opts.showNotifyNewEvents)
    add(
      'new_event_notice',
      'new_event_notice',
      ...own(values.discord_new_event_channel_id),
    );
  add(
    'start_mention',
    'start_mention',
    values.discord_post_signups ? signup || fallback : null,
  );
  if (opts.showSignupReminder ?? opts.isRepeater)
    add('signup_reminder', 'signup_reminder_dm');
  return checks;
}
