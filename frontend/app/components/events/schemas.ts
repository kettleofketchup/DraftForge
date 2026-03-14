import { z } from 'zod';

export const GameType = { DOTA2: 1, DEADLOCK: 2 } as const;

export const EventState = {
  UPCOMING: 'upcoming', SIGNUPS_OPEN: 'signups_open', ROLL_CALL: 'roll_call',
  IN_PROGRESS: 'in_progress', COMPLETED: 'completed', CANCELLED: 'cancelled',
} as const;

export const SignupStatus = {
  RSVP: 'rsvp', PENDING_APPROVAL: 'pending_approval', APPROVED: 'approved',
  CONFIRMED: 'confirmed', WAITLISTED: 'waitlisted', REJECTED: 'rejected', CANCELLED: 'cancelled',
} as const;

export const eventSchema = z.object({
  id: z.number(),
  organization: z.number(),
  organization_name: z.string(),
  event_repeater: z.number().nullable(),
  name: z.string(),
  description: z.string(),
  scheduled_at: z.string(),
  signups_open_at: z.string().nullable(),
  state: z.string(),
  tournament: z.number().nullable(),
  created_by: z.number().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
  signup_count: z.number(),
  confirmed_count: z.number(),
  tournament_name: z.string(),
  tournament_league: z.number(),
  tournament_type: z.string(),
  game_type: z.number(),
  draft_type: z.string(),
  people_per_team: z.number(),
  number_of_teams: z.number(),
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
  auto_start: z.boolean(),
});

export type EventType = z.infer<typeof eventSchema>;

export const eventSignupSchema = z.object({
  id: z.number(),
  event: z.number(),
  user: z.number(),
  username: z.string().nullable(),
  user_avatar: z.string().nullable(),
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

export const createEventInputSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  description: z.string(),
  scheduled_at: z.string(),
  organization: z.number(),
  tournament_league: z.number({ error: 'League is required' }),
  tournament_name: z.string().min(1, 'Tournament name is required'),
  tournament_type: z.string(),
  game_type: z.number(),
  draft_type: z.string(),
  people_per_team: z.number().int().min(1),
  number_of_teams: z.number().int().min(2).nullable(),
  // Recurring fields
  is_recurring: z.boolean(),
  frequency: z.string().optional(),
  day_of_week: z.number().int().min(0).max(6).optional(),
  time_of_day: z.string().optional(),
  starts_at: z.string().optional(),
  ends_at: z.string().optional(),
  generate_days_ahead: z.number().int().min(1),
});

export type CreateEventInput = z.infer<typeof createEventInputSchema>;
