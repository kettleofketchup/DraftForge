import { z } from 'zod';

export const EventState = {
  UPCOMING: 'upcoming', SIGNUPS_OPEN: 'signups_open', ROLL_CALL: 'roll_call',
  IN_PROGRESS: 'in_progress', COMPLETED: 'completed', CANCELLED: 'cancelled',
} as const;

export const SignupStatus = {
  RSVP: 'rsvp', PENDING_APPROVAL: 'pending_approval', APPROVED: 'approved',
  CONFIRMED: 'confirmed', WAITLISTED: 'waitlisted', TENTATIVE: 'tentative',
  REJECTED: 'rejected', CANCELLED: 'cancelled',
} as const;

export const GameMode = {
  NORMAL: 'normal', CAPTAINS_MODE: 'captains_mode', TURBO: 'turbo', CUSTOM: 'custom',
} as const;

export const eventSchema = z.object({
  id: z.number(),
  organization: z.number(),
  organization_name: z.string(),
  event_repeater: z.number().nullable(),
  event_repeater_name: z.string().nullable(),
  name: z.string(),
  description: z.string(),
  scheduled_at: z.string(),
  signups_open_at: z.string().nullable(),
  state: z.nativeEnum(EventState),
  tournament: z.number().nullable(),
  created_by: z.number().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
  signup_count: z.number(),
  confirmed_count: z.number(),
  tournament_name: z.string(),
  tournament_league: z.number().nullable(),
  tournament_type: z.string(),
  game_type: z.number(),
  draft_type: z.string(),
  game_mode: z.string(),
  custom_game_name: z.string(),
  captains_draft_time: z.number(),
  lobby_steam_league_id: z.number().nullable(),
  people_per_team: z.number(),
  number_of_teams: z.number().nullable(),
  tournament_date: z.string().nullable(),
  timezone: z.string(),
  min_players: z.number().nullable(),
  max_players: z.number().nullable(),
  signup_deadline_hours: z.number().nullable(),
  allow_team_signups: z.boolean(),
  allow_user_signups: z.boolean(),
  auto_approve: z.boolean(),
  auto_confirm: z.boolean(),
  require_mmr_verified: z.boolean(),
  require_steam_id: z.boolean(),
  require_profile_complete: z.boolean(),
  roll_call_enabled: z.boolean(),
  roll_call_mode: z.string(),
  allow_active_mmr: z.boolean(),
  allow_previous_rank: z.boolean(),
  allow_battlecup_rating: z.boolean(),
  discord_create_event: z.boolean(),
  discord_sync_signups: z.boolean(),
  discord_event_title: z.string(),
  discord_event_description: z.string(),
  discord_event_info: z.string(),
  discord_signup_reminder: z.boolean(),
  discord_signup_reminder_hours: z.number(),
  discord_confirm_attendance: z.boolean(),
  discord_confirm_attendance_hours: z.number(),
  discord_profile_reminder: z.boolean(),
  discord_profile_reminder_hours: z.number(),
  discord_mark_interested: z.boolean(),
  discord_post_signups: z.boolean(),
  discord_post_signups_channel_id: z.string(),
  discord_announcement: z.boolean(),
  discord_announcement_channel_id: z.string(),
  discord_announcement_hours: z.number(),
  discord_announcement_role_ids: z.array(z.string()).default([]),
  discord_signup_role_ids: z.array(z.string()).default([]),
  discord_subscriber_dm: z.boolean().optional(),
  discord_subscriber_dm_hours: z.number().optional(),
  discord_require_rank_screenshot: z.boolean(),
  discord_require_battlecup_screenshot: z.boolean(),
  min_mmr: z.number().nullable(),
  user_can_manage: z.boolean().default(false),
  _warning: z.string().optional(),
}).superRefine((val, ctx) => {
  // Single events have no subscriber list — discord_signup_reminder DMs
  // subscribed users, which is a series-level concept on EventRepeater.
  // Mirrors the backend EventSerializer.validate rejection (Task 2.2).
  if (val.event_repeater === null && val.discord_signup_reminder === true) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['discord_signup_reminder'],
      message:
        'Signup reminder DMs require a recurring event series — single events have no subscribers.',
    });
  }
});

export type EventType = z.infer<typeof eventSchema>;

export const eventSignupSchema = z.object({
  id: z.number(),
  event: z.number(),
  user: z.number(),
  username: z.string().nullable(),
  user_avatar: z.string().nullable(),
  user_data: z.object({
    pk: z.number(),
    username: z.string(),
    nickname: z.string().nullable(),
    avatar: z.string().nullable(),
    discordId: z.string().nullable(),
    discordNickname: z.string().nullable(),
    positions: z.object({
      carry: z.number(),
      mid: z.number(),
      offlane: z.number(),
      soft_support: z.number(),
      hard_support: z.number(),
    }).nullable(),
    steam_account_id: z.number().nullable(),
    avatarUrl: z.string().nullable(),
  }).nullable(),
  dota_profile: z.object({
    positions: z.object({
      pos_1: z.boolean(),
      pos_2: z.boolean(),
      pos_3: z.boolean(),
      pos_4: z.boolean(),
      pos_5: z.boolean(),
    }),
    rank_status: z.string(),
    rank_medal: z.string().nullable(),
    mmr: z.number().nullable(),
    rank_screenshot: z.string().nullable(),
    battlecup_screenshot: z.string().nullable(),
    battle_cup_tier: z.number().nullable(),
  }).nullable(),
  org_user_mmr: z.number().nullable().default(null),
  org_user_pk: z.number().nullable().default(null),
  organization: z.number().nullable().default(null),
  suggested_mmr: z.number().int(),
  suggested_mmr_range: z.tuple([z.number().int(), z.number().int()]),
  suggested_mmr_range_source: z.enum(['medal', 'battle_cup', 'fallback']),
  event_team: z.number().nullable(),
  signup_type: z.string(),
  status: z.string(),
  waitlist_position: z.number().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});

export type EventSignupType = z.infer<typeof eventSignupSchema>;

export const eventTeamSchema = z.object({
  id: z.number(),
  event: z.number(),
  name: z.string(),
  captain: z.number(),
  captain_name: z.string().nullable(),
  member_count: z.number(),
  created_at: z.string(),
  updated_at: z.string(),
});

export type EventTeamType = z.infer<typeof eventTeamSchema>;

export const Frequency = {
  DAILY: 'daily', WEEKLY: 'weekly', EVERY_TWO_WEEKS: 'every_two_weeks', MONTHLY: 'monthly',
} as const;

export const FREQUENCY_LABELS: Record<string, string> = {
  [Frequency.DAILY]: 'Daily',
  [Frequency.WEEKLY]: 'Weekly',
  [Frequency.EVERY_TWO_WEEKS]: 'Every Two Weeks',
  [Frequency.MONTHLY]: 'Monthly',
};

export const DAY_LABELS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

export const COMMON_TIMEZONES = [
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'America/Phoenix',
  'America/Anchorage',
  'Pacific/Honolulu',
  'America/Toronto',
  'America/Vancouver',
  'America/Sao_Paulo',
  'Europe/London',
  'Europe/Paris',
  'Europe/Berlin',
  'Europe/Moscow',
  'Asia/Dubai',
  'Asia/Kolkata',
  'Asia/Singapore',
  'Asia/Tokyo',
  'Asia/Shanghai',
  'Asia/Seoul',
  'Australia/Sydney',
  'Australia/Melbourne',
  'Pacific/Auckland',
  'UTC',
] as const;

/**
 * Convert a naive datetime-local string to UTC ISO string using the given IANA timezone.
 * datetime-local gives "2026-03-29T19:00" — this interprets it as 7 PM in the given tz
 * and converts to UTC for the API.
 *
 * Uses Intl.DateTimeFormat to compute the UTC offset for the target timezone at the
 * given date/time, which correctly handles DST transitions.
 */
export function localToUTC(datetimeLocal: string, timezone: string): string {
  if (!datetimeLocal || !timezone) return datetimeLocal;

  // Parse the naive datetime parts (YYYY-MM-DDTHH:MM)
  const [datePart, timePart] = datetimeLocal.split('T');
  const [year, month, day] = datePart.split('-').map(Number);
  const [hour, minute] = (timePart || '00:00').split(':').map(Number);

  // Create a UTC date with these exact numbers
  const utcGuess = Date.UTC(year, month - 1, day, hour, minute);

  // Find what that UTC instant looks like in the target timezone
  const fmt = new Intl.DateTimeFormat('en-US', {
    timeZone: timezone,
    year: 'numeric', month: 'numeric', day: 'numeric',
    hour: 'numeric', minute: 'numeric', hour12: false,
  });
  const parts = Object.fromEntries(
    fmt.formatToParts(new Date(utcGuess)).map((p) => [p.type, p.value])
  );
  const tzHour = Number(parts.hour === '24' ? '0' : parts.hour);
  const tzMinute = Number(parts.minute);
  const tzDay = Number(parts.day);

  // Offset = difference between what we want (the naive values) and what the tz shows
  let diffMinutes = (hour - tzHour) * 60 + (minute - tzMinute);
  // Handle day boundary crossing
  if (tzDay !== day) {
    diffMinutes += (day - tzDay) * 24 * 60;
  }

  const result = new Date(utcGuess + diffMinutes * 60_000);
  return result.toISOString();
}

export const discordConfigSchema = z.object({
  discord_create_event: z.boolean(),
  discord_sync_signups: z.boolean(),
  discord_event_title: z.string(),
  discord_event_description: z.string(),
  discord_event_info: z.string(),
  discord_signup_reminder: z.boolean(),
  discord_signup_reminder_hours: z.number().int().min(1),
  discord_confirm_attendance: z.boolean(),
  discord_confirm_attendance_hours: z.number().int().min(1),
  discord_profile_reminder: z.boolean(),
  discord_profile_reminder_hours: z.number().int().min(1),
  discord_mark_interested: z.boolean(),
  discord_post_signups: z.boolean(),
  discord_post_signups_channel_id: z.string(),
  discord_announcement: z.boolean(),
  discord_announcement_channel_id: z.string(),
  discord_announcement_hours: z.number().int().min(1),
  discord_announcement_role_ids: z.array(z.string()).default([]),
  discord_signup_role_ids: z.array(z.string()).default([]),
  discord_subscriber_dm: z.boolean().optional(),
  discord_subscriber_dm_hours: z.number().int().min(1).optional(),
  discord_require_rank_screenshot: z.boolean(),
  discord_require_battlecup_screenshot: z.boolean(),
  min_mmr: z.number().int().min(0).nullable(),
  allow_active_mmr: z.boolean(),
  allow_previous_rank: z.boolean(),
  allow_battlecup_rating: z.boolean(),
});

export const DISCORD_CONFIG_DEFAULTS = {
  discord_create_event: false,
  discord_sync_signups: false,
  discord_event_title: '',
  discord_event_description: '',
  discord_event_info: '',
  discord_signup_reminder: true,
  discord_signup_reminder_hours: 24,
  discord_confirm_attendance: false,
  discord_confirm_attendance_hours: 2,
  discord_profile_reminder: false,
  discord_profile_reminder_hours: 24,
  discord_mark_interested: false,
  discord_post_signups: false,
  discord_post_signups_channel_id: '',
  discord_announcement: false,
  discord_announcement_channel_id: '',
  discord_announcement_hours: 24,
  discord_announcement_role_ids: [] as string[],
  discord_signup_role_ids: [] as string[],
  discord_require_rank_screenshot: false,
  discord_require_battlecup_screenshot: false,
  min_mmr: null as number | null,
  allow_active_mmr: true,
  allow_previous_rank: true,
  allow_battlecup_rating: true,
} as const;

export const createEventInputSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  description: z.string(),
  scheduled_at: z.string(),
  organization: z.number(),
  tournament_league: z.number().nullable().optional(),
  tournament_name: z.string().min(1, 'Tournament name is required'),
  tournament_type: z.string(),
  game_type: z.number(),
  draft_type: z.string(),
  game_mode: z.string(),
  custom_game_name: z.string(),
  captains_draft_time: z.number().int().min(1),
  lobby_steam_league_id: z.number().nullable(),
  people_per_team: z.number().int().min(1),
  number_of_teams: z.number().int().min(2).nullable(),
  timezone: z.string().min(1, 'Timezone is required'),
  discord_notify_new_events: z.boolean().optional(),
  signup_mode: z.enum(['immediate', 'scheduled', 'manual']),
  signup_days_before: z.number().int().min(1).optional(),
  // Recurring fields
  is_recurring: z.boolean(),
  frequency: z.string().optional(),
  day_of_week: z.number().int().min(0).max(6).optional(),
  time_of_day: z.string().optional(),
  starts_at: z.string().optional(),
  ends_at: z.string().optional(),
  generate_days_ahead: z.number().int().min(1),
}).merge(discordConfigSchema);

export type CreateEventInput = z.infer<typeof createEventInputSchema>;

export const discordEventMsgSchema = z.object({
  id: z.number(),
  channel_id: z.string(),
  channel_type: z.string(),
  message_id: z.string().nullable(),
  thread_id: z.string().nullable(),
  has_posted: z.boolean(),
  message_last_updated: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});

export const LogCategory = {
  SYSTEM: 1,
  INTERACTION: 2,
  SIGNUP: 3,
  NOTIFICATION: 4,
} as const;

export const LOG_CATEGORY_LABELS: Record<number, string> = {
  [LogCategory.SYSTEM]: 'System',
  [LogCategory.INTERACTION]: 'Interaction',
  [LogCategory.SIGNUP]: 'Signup',
  [LogCategory.NOTIFICATION]: 'Notification',
};

export const discordEventLogSchema = z.object({
  id: z.number(),
  category: z.number(),
  category_display: z.string(),
  action: z.string(),
  target_type: z.string(),
  discord_user_id: z.string(),
  discord_username: z.string(),
  message_id: z.string().nullable(),
  status_code: z.number().nullable(),
  error_message: z.string(),
  success: z.boolean(),
  created_at: z.string(),
});

export const discordEventDMSchema = z.object({
  id: z.number(),
  dm_type: z.number(),
  dm_type_display: z.string(),
  username: z.string().nullable(),
  nickname: z.string().nullable(),
  discord_user_id: z.string().nullable(),
  can_send: z.boolean(),
  message_id: z.string(),
  sent_at: z.string().nullable(),
  delivered: z.boolean(),
  responded: z.boolean(),
  response_text: z.string(),
  responded_at: z.string().nullable(),
  created_at: z.string(),
});

export const discordEventStateSchema = z.object({
  id: z.number(),
  guild_id: z.string(),
  scheduled_event_id: z.string().nullable(),
  signup_message: discordEventMsgSchema.nullable(),
  announcement: discordEventMsgSchema.nullable(),
  logs: z.array(discordEventLogSchema),
  dms: z.array(discordEventDMSchema),
  created_at: z.string(),
  updated_at: z.string(),
});

export type DiscordEventState = z.infer<typeof discordEventStateSchema>;
