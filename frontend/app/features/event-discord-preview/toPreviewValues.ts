import {
  toRepeaterCreatePayload,
  type RepeaterScheduleInput,
} from '~/components/events/createEventPayload';
import { localToUTC } from '~/components/events/schemas';
import type { PreviewValuesMode } from './context';

// Mirrors backend events/discord/preview_values.py PREVIEW_EVENT_FIELDS.
const SHARED_FIELDS = [
  'discord_create_event',
  'discord_sync_signups',
  'discord_event_title',
  'discord_event_description',
  'discord_event_info',
  'discord_signup_reminder',
  'discord_signup_reminder_hours',
  'discord_confirm_attendance',
  'discord_confirm_attendance_hours',
  'discord_profile_reminder',
  'discord_profile_reminder_hours',
  'discord_mark_interested',
  'discord_post_signups',
  'discord_post_signups_channel_id',
  'discord_announcement',
  'discord_announcement_channel_id',
  'discord_announcement_hours',
  'discord_announcement_role_ids',
  'discord_signup_role_ids',
  'discord_start_mention',
  'discord_start_mention_minutes',
  'discord_start_mention_scope',
  'discord_require_rank_screenshot',
  'discord_require_battlecup_screenshot',
  'min_mmr',
  'event_voice_channel_id',
  'voice_presence_confirms',
  'name',
  'description',
  'timezone',
  'max_players',
  'allow_user_signups',
  'game_type',
  'require_steam_id',
  'require_mmr_verified',
  'require_profile_complete',
  'signup_open_mode',
  'signups_open_hours_before',
] as const;

// Blank is a real value for these (e.g. a cleared title falls back to the event name).
const BLANK_ALLOWED = new Set<string>([
  'name',
  'description',
  'discord_event_title',
  'discord_event_description',
  'discord_event_info',
  'discord_post_signups_channel_id',
  'discord_announcement_channel_id',
  'event_voice_channel_id',
]);

type FormValues = Record<string, unknown>;

function keep(key: string, value: unknown): boolean {
  if (value === undefined) return false;
  if (value === '') return BLANK_ALLOWED.has(key);
  if (value === null) return key !== 'timezone';
  return true;
}

function pick(form: FormValues, out: Record<string, unknown>): void {
  for (const key of SHARED_FIELDS) {
    if (key in form && keep(key, form[key])) out[key] = form[key];
  }
}

function utc(local: unknown, timezone: unknown): string | undefined {
  if (typeof local !== 'string' || local === '') return undefined;
  return localToUTC(local, typeof timezone === 'string' ? timezone : '');
}

/** Whitelisted form values for a preview request, converted the way the modals submit them. */
export function toPreviewValues(
  form: FormValues,
  mode: PreviewValuesMode,
  { creating = false }: { creating?: boolean } = {},
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  pick(form, out);
  if (mode === 'event') {
    const scheduledAt = utc(form.scheduled_at, form.timezone);
    if (scheduledAt) out.scheduled_at = scheduledAt;
    const endsAt = utc(form.event_ends_at, form.timezone);
    if (endsAt) out.ends_at = endsAt;
    return out;
  }
  const schedule: Partial<ReturnType<typeof toRepeaterCreatePayload>> =
    toRepeaterCreatePayload(form as RepeaterScheduleInput);
  // Editing a series has no start date field and does not send one.
  if (!creating) delete schedule.starts_at;
  for (const [key, value] of Object.entries(schedule)) {
    if (value !== undefined) out[key] = value;
  }
  return out;
}
