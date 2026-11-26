import { EVENT_SECTION_FIELDS } from './form/settingsFields';

export interface FallbackChannelFlags {
  announcement?: boolean;
  postSignups?: boolean;
  signupChannelId?: string;
  confirmAttendance?: boolean;
  attendanceChannelId?: string;
  profileReminder?: boolean;
  profileChannelId?: string;
  notifyNewEvents?: boolean;
  newEventChannelId?: string;
  showNotifyNewEvents: boolean;
}

const label = (field: string): string =>
  EVENT_SECTION_FIELDS.discord[field].label;

export function fallbackChannelUsers({
  announcement,
  postSignups,
  signupChannelId,
  confirmAttendance,
  attendanceChannelId,
  profileReminder,
  profileChannelId,
  notifyNewEvents,
  newEventChannelId,
  showNotifyNewEvents,
}: FallbackChannelFlags): string[] {
  const users: string[] = [];
  if (announcement) users.push(label('discord_announcement'));
  if (announcement && postSignups && !signupChannelId) {
    users.push(label('discord_post_signups'));
  }
  if (confirmAttendance && !attendanceChannelId) {
    users.push(label('discord_confirm_attendance'));
  }
  if (profileReminder && !profileChannelId) {
    users.push(label('discord_profile_reminder'));
  }
  if (showNotifyNewEvents && notifyNewEvents && !newEventChannelId) {
    users.push(label('discord_notify_new_events'));
  }
  return users;
}
