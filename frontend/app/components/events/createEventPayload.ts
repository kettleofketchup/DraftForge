import type { SignupOpenMode } from './schemas';

export type RepeaterScheduleInput = {
  frequency?: string;
  day_of_week?: number | null;
  time_of_day?: string;
  starts_at?: string;
  ends_at?: string | null;
  generate_days_ahead?: number;
  discord_notify_new_events?: boolean;
};

export type RepeaterSchedulePayload = {
  discord_notify_new_events: boolean;
  frequency: string | undefined;
  day_of_week: number | null;
  time_of_day: string;
  starts_at: string;
  ends_at: string | null;
  generate_days_ahead: number | undefined;
};

/** Series schedule fields as CreateEventModal sends them, blanks filled with the create defaults. */
export function toRepeaterCreatePayload(
  data: RepeaterScheduleInput,
): RepeaterSchedulePayload {
  return {
    discord_notify_new_events: data.discord_notify_new_events ?? false,
    frequency: data.frequency,
    day_of_week: data.day_of_week ?? null,
    time_of_day: data.time_of_day || '19:00',
    starts_at: data.starts_at || new Date().toISOString().slice(0, 10),
    ends_at: data.ends_at || null,
    generate_days_ahead: data.generate_days_ahead,
  };
}

export function openSignupsFromForm(data: {
  signup_open_mode?: SignupOpenMode;
}): boolean {
  return data.signup_open_mode === 'immediate';
}
