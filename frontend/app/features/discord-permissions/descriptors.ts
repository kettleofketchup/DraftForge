import type { DiscordFields } from '~/components/events/DiscordConfigSection';
import { EVENT_SECTION_FIELDS } from '~/components/events/form/settingsFields';
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
  const notice = !!(values.discord_post_signups && signup);
  add(
    'announcement',
    notice ? 'announcement' : 'signup_fallback',
    announcement,
    notice ? values.discord_announcement_role_ids : [],
    !notice && !!announcement,
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

export type ChannelPicker =
  | 'signup_post'
  | 'announcement'
  | 'attendance_reminder'
  | 'profile_reminder'
  | 'new_event_notice';

const PICKER_FIELDS: Record<ChannelPicker, keyof DiscordFields> = {
  announcement: 'discord_announcement_channel_id',
  signup_post: 'discord_post_signups_channel_id',
  attendance_reminder: 'discord_confirm_attendance_channel_id',
  profile_reminder: 'discord_profile_reminder_channel_id',
  new_event_notice: 'discord_new_event_channel_id',
};

const NATIVE_PICKER: Record<string, ChannelPicker> = {
  signup_post: 'signup_post',
  signup_fallback: 'announcement',
  announcement: 'announcement',
  attendance_reminder: 'attendance_reminder',
  profile_reminder: 'profile_reminder',
  new_event_notice: 'new_event_notice',
};

export const SETTING_LABELS: Record<string, string> = {
  signup_post: EVENT_SECTION_FIELDS.discord.discord_post_signups.label,
  signup_fallback: EVENT_SECTION_FIELDS.discord.discord_post_signups.label,
  announcement: EVENT_SECTION_FIELDS.discord.discord_announcement.label,
  attendance_reminder:
    EVENT_SECTION_FIELDS.discord.discord_confirm_attendance.label,
  profile_reminder: EVENT_SECTION_FIELDS.discord.discord_profile_reminder.label,
  new_event_notice:
    EVENT_SECTION_FIELDS.discord.discord_notify_new_events.label,
};

export type ChannelGroup = {
  channelId: string | null;
  checks: CheckDescriptor[];
};

export function isSettingEnabled(values: DiscordFields, key: string): boolean {
  const operation = SETTINGS_OPERATIONS[key];
  return !!operation && !!values[operation.field];
}

/** Groups enabled channel checks under the one picker that shows the channel
 *  they send to: a channel picked in several places is badged once. */
export function channelPermissionGroups(
  values: DiscordFields,
  descriptors: readonly CheckDescriptor[],
): Map<ChannelPicker, ChannelGroup> {
  const enabled = descriptors.filter(
    (d) => d.key in NATIVE_PICKER && isSettingEnabled(values, d.key),
  );
  const picked = (picker: ChannelPicker) =>
    (values[PICKER_FIELDS[picker]] as string | undefined) || null;
  const visible = new Set<ChannelPicker>();
  for (const d of enabled)
    visible.add(d.fallback ? 'announcement' : NATIVE_PICKER[d.key]);
  if (values.discord_announcement) visible.add('announcement');
  const order = Object.keys(PICKER_FIELDS) as ChannelPicker[];
  const groups = new Map<ChannelPicker, ChannelGroup>();
  for (const d of enabled) {
    const native = d.fallback ? 'announcement' : NATIVE_PICKER[d.key];
    const owner =
      (d.channel_id &&
        order.find((p) => visible.has(p) && picked(p) === d.channel_id)) ||
      native;
    const group = groups.get(owner) ?? { channelId: d.channel_id, checks: [] };
    group.checks.push(d);
    groups.set(owner, group);
  }
  return groups;
}

/** The setting a check belongs to, plus how it reached this channel. */
export function channelUseLabel(
  descriptor: CheckDescriptor,
  values: DiscordFields,
): string {
  const label = SETTING_LABELS[descriptor.key] ?? descriptor.key;
  if (descriptor.key === 'signup_fallback')
    return values.discord_post_signups_channel_id
      ? `${label} (announcement fallback)`
      : `${label} (no signup channel; uses the announcement channel)`;
  if (descriptor.key !== 'announcement' && descriptor.fallback)
    return `${label} (no channel of its own; uses the announcement channel)`;
  return label;
}
