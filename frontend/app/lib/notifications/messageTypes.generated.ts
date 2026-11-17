// GENERATED FILE - DO NOT EDIT.
// Source: backend/notifications/registry.py
// Regenerate with: just py::gen-message-types
import { z } from 'zod';

export const MESSAGE_CHANNELS = ['dm', 'ephemeral', 'channel_post'] as const;
export const MESSAGE_AUDIENCES = [
  'signup',
  'subscriber',
  'tournament_participant',
  'match_player',
] as const;
export const MESSAGE_GROUP_KEYS = [
  'signup_receipts',
  'attendance',
  'roster_changes',
  'pre_game_reminders',
  'series_updates',
  'match_links',
  'conduct',
] as const;
export const MESSAGE_KEYS = [
  'rsvp.signup_receipt',
  'rsvp.reachability_check',
  'rsvp.confirm_request',
  'rsvp.escalation_nudge',
  'event.attendance_reminder',
  'rsvp.promotion',
  'rsvp.roster_change',
  'rsvp.drop_notice',
  'rsvp.event_cancelled',
  'rsvp.pre_game_reminder',
  'event.profile_reminder',
  'series.signup_reminder',
  'tournament.draft_link',
  'tournament.herodraft_link',
  'lobby.info',
] as const;

export const MessageChannelSchema = z.enum(MESSAGE_CHANNELS);
export type MessageChannel = z.infer<typeof MessageChannelSchema>;

export const MessageAudienceSchema = z.enum(MESSAGE_AUDIENCES);
export type MessageAudience = z.infer<typeof MessageAudienceSchema>;

export const MessageGroupKeySchema = z.enum(MESSAGE_GROUP_KEYS);
export type MessageGroupKey = z.infer<typeof MessageGroupKeySchema>;

export const MessageKeySchema = z.enum(MESSAGE_KEYS);
export type MessageKey = z.infer<typeof MessageKeySchema>;

export const MessageGroupSchema = z.object({
  key: MessageGroupKeySchema,
  label: z.string().min(1),
  description: z.string().min(1),
  optOutableDefault: z.boolean(),
  essentialLocked: z.boolean(),
});
export type MessageGroup = z.infer<typeof MessageGroupSchema>;

export const MessageTypeSchema = z.object({
  key: MessageKeySchema,
  group: MessageGroupKeySchema,
  label: z.string().min(1),
  description: z.string().min(1),
  audience: MessageAudienceSchema,
  channels: z.array(MessageChannelSchema).min(1),
  essentialDefault: z.boolean(),
  essentialLocked: z.boolean(),
  urgent: z.boolean(),
});
export type MessageType = z.infer<typeof MessageTypeSchema>;

export const MESSAGE_GROUPS: readonly MessageGroup[] = [
  {
    key: 'signup_receipts',
    label: 'Sign-up receipts',
    description: 'Confirmation that your sign-up for an event was received.',
    optOutableDefault: false,
    essentialLocked: false,
  },
  {
    key: 'attendance',
    label: 'Attendance checks',
    description:
      'Requests to confirm you will attend an event you signed up for.',
    optOutableDefault: false,
    essentialLocked: false,
  },
  {
    key: 'roster_changes',
    label: 'Roster changes',
    description: 'Changes to your place on an event roster or waitlist.',
    optOutableDefault: true,
    essentialLocked: false,
  },
  {
    key: 'pre_game_reminders',
    label: 'Pre-game reminders',
    description: 'Reminders shortly before an event you signed up for starts.',
    optOutableDefault: true,
    essentialLocked: false,
  },
  {
    key: 'series_updates',
    label: 'Series updates',
    description: 'News about recurring event series you subscribe to.',
    optOutableDefault: true,
    essentialLocked: false,
  },
  {
    key: 'match_links',
    label: 'Match links',
    description: 'Draft, hero draft and lobby details for matches you play in.',
    optOutableDefault: false,
    essentialLocked: false,
  },
  {
    key: 'conduct',
    label: 'Conduct',
    description: 'Messages from organizers about conduct. Always delivered.',
    optOutableDefault: false,
    essentialLocked: true,
  },
];

export const MESSAGE_TYPES: readonly MessageType[] = [
  {
    key: 'rsvp.signup_receipt',
    group: 'signup_receipts',
    label: 'Sign-up receipt',
    description: 'Sent when you sign up for an event.',
    audience: 'signup',
    channels: ['dm', 'ephemeral'],
    essentialDefault: false,
    essentialLocked: false,
    urgent: false,
  },
  {
    key: 'rsvp.reachability_check',
    group: 'signup_receipts',
    label: 'Reachability check',
    description:
      'Sent on your first sign-up for an event with a ready check, to confirm DraftForge can reach you.',
    audience: 'signup',
    channels: ['dm', 'ephemeral'],
    essentialDefault: true,
    essentialLocked: false,
    urgent: false,
  },
  {
    key: 'rsvp.confirm_request',
    group: 'attendance',
    label: 'Confirm attendance',
    description:
      'Asks you to confirm you will attend, with the no-show policy.',
    audience: 'signup',
    channels: ['dm'],
    essentialDefault: true,
    essentialLocked: false,
    urgent: false,
  },
  {
    key: 'rsvp.escalation_nudge',
    group: 'attendance',
    label: 'Confirmation deadline',
    description: 'A final nudge when your attendance confirmation is overdue.',
    audience: 'signup',
    channels: ['dm'],
    essentialDefault: true,
    essentialLocked: false,
    urgent: true,
  },
  {
    key: 'event.attendance_reminder',
    group: 'attendance',
    label: 'Attendance reminder',
    description: 'Reminds you to confirm your attendance for an event.',
    audience: 'signup',
    channels: ['dm'],
    essentialDefault: false,
    essentialLocked: false,
    urgent: false,
  },
  {
    key: 'rsvp.promotion',
    group: 'roster_changes',
    label: 'Promoted from waitlist',
    description:
      'You moved off the waitlist into the roster. Withdraw at once if you cannot attend.',
    audience: 'signup',
    channels: ['dm'],
    essentialDefault: true,
    essentialLocked: false,
    urgent: true,
  },
  {
    key: 'rsvp.roster_change',
    group: 'roster_changes',
    label: 'Roster change',
    description: 'Staff rejected, removed, moved or reinstated your sign-up.',
    audience: 'signup',
    channels: ['dm'],
    essentialDefault: false,
    essentialLocked: false,
    urgent: false,
  },
  {
    key: 'rsvp.drop_notice',
    group: 'roster_changes',
    label: 'Dropped from roster',
    description:
      'You were dropped from the roster, for example after a missed check.',
    audience: 'signup',
    channels: ['dm'],
    essentialDefault: false,
    essentialLocked: false,
    urgent: false,
  },
  {
    key: 'rsvp.event_cancelled',
    group: 'roster_changes',
    label: 'Event cancelled',
    description: 'An event you signed up for was cancelled.',
    audience: 'signup',
    channels: ['dm'],
    essentialDefault: false,
    essentialLocked: false,
    urgent: false,
  },
  {
    key: 'rsvp.pre_game_reminder',
    group: 'pre_game_reminders',
    label: 'Pre-game reminder',
    description: 'Sent shortly before an event you are rostered for starts.',
    audience: 'signup',
    channels: ['dm'],
    essentialDefault: false,
    essentialLocked: false,
    urgent: false,
  },
  {
    key: 'event.profile_reminder',
    group: 'pre_game_reminders',
    label: 'Profile reminder',
    description: 'Asks you to complete your profile before an event.',
    audience: 'signup',
    channels: ['dm'],
    essentialDefault: false,
    essentialLocked: false,
    urgent: false,
  },
  {
    key: 'series.signup_reminder',
    group: 'series_updates',
    label: 'Series sign-up reminder',
    description:
      'A new event in a series you subscribe to is open for sign-up.',
    audience: 'subscriber',
    channels: ['dm'],
    essentialDefault: false,
    essentialLocked: false,
    urgent: false,
  },
  {
    key: 'tournament.draft_link',
    group: 'match_links',
    label: 'Team draft link',
    description: 'The link to the team draft of a tournament you are in.',
    audience: 'tournament_participant',
    channels: ['dm'],
    essentialDefault: false,
    essentialLocked: false,
    urgent: false,
  },
  {
    key: 'tournament.herodraft_link',
    group: 'match_links',
    label: 'Hero draft link',
    description: 'The link to the hero draft of a match you play in.',
    audience: 'match_player',
    channels: ['dm'],
    essentialDefault: false,
    essentialLocked: false,
    urgent: false,
  },
  {
    key: 'lobby.info',
    group: 'match_links',
    label: 'Lobby details',
    description: 'The lobby name, password and your side for a match.',
    audience: 'match_player',
    channels: ['dm'],
    essentialDefault: false,
    essentialLocked: false,
    urgent: false,
  },
];
