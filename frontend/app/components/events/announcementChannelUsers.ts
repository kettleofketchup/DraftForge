export interface AnnouncementChannelFlags {
  announcement?: boolean;
  confirmAttendance?: boolean;
  profileReminder?: boolean;
  notifyNewEvents?: boolean;
  showNotifyNewEvents: boolean;
}

export function announcementChannelUsers({
  announcement,
  confirmAttendance,
  profileReminder,
  notifyNewEvents,
  showNotifyNewEvents,
}: AnnouncementChannelFlags): string[] {
  const users: string[] = [];
  if (announcement) users.push('Pre-day announcement');
  if (confirmAttendance) users.push('Attendance reminder');
  if (profileReminder) users.push('Profile reminder');
  if (showNotifyNewEvents && notifyNewEvents) {
    users.push('Message interested users (new-event posts)');
  }
  return users;
}
