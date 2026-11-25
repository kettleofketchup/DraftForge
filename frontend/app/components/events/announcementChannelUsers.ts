import { EVENT_SECTION_FIELDS } from './form/settingsFields';

export interface AnnouncementChannelFlags {
  announcement?: boolean;
  confirmAttendance?: boolean;
  profileReminder?: boolean;
  notifyNewEvents?: boolean;
  showNotifyNewEvents: boolean;
}

const label = (field: string): string =>
  EVENT_SECTION_FIELDS.discord[field].label;

export function announcementChannelUsers({
  announcement,
  confirmAttendance,
  profileReminder,
  notifyNewEvents,
  showNotifyNewEvents,
}: AnnouncementChannelFlags): string[] {
  const users: string[] = [];
  if (announcement) users.push(label('discord_announcement'));
  if (confirmAttendance) users.push(label('discord_confirm_attendance'));
  if (profileReminder) users.push(label('discord_profile_reminder'));
  if (showNotifyNewEvents && notifyNewEvents) {
    users.push(label('discord_notify_new_events'));
  }
  return users;
}
