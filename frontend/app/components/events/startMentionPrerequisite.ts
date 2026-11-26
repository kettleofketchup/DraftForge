// Mirrors has_signup_post in backend/events/views.py (get_event_task_schedule).

export type SignupReason = 'signup_disabled' | 'signup_no_channel';

export type StartMentionPrerequisite =
  | { kind: 'ok' }
  | { kind: 'announcement_fallback'; reason: SignupReason }
  | { kind: 'missing'; reason: SignupReason; announcementOn: boolean };

export interface StartMentionPrerequisiteInput {
  postSignups: boolean | undefined;
  signupChannelId: string | null | undefined;
  announcement: boolean | undefined;
  announcementChannelId: string | null | undefined;
}

export const START_MENTION_PREREQUISITE_NOTE =
  "Replies to the event's signup post, which must already be posted when the mention is due. If it isn't posted yet, the mention is retried until roll call ends and may go out late or not at all.";

export function startMentionPrerequisite({
  postSignups,
  signupChannelId,
  announcement,
  announcementChannelId,
}: StartMentionPrerequisiteInput): StartMentionPrerequisite {
  if (postSignups && signupChannelId) return { kind: 'ok' };
  const reason: SignupReason = postSignups
    ? 'signup_no_channel'
    : 'signup_disabled';
  if (announcement && announcementChannelId) {
    return { kind: 'announcement_fallback', reason };
  }
  return { kind: 'missing', reason, announcementOn: !!announcement };
}

const FALLBACK_MESSAGES: Record<SignupReason, string> = {
  signup_disabled:
    'Signup posts are off, so the signup embed is posted in the announcement channel and the mention replies there.',
  signup_no_channel:
    'No signup channel is selected, so the signup embed is posted in the announcement channel and the mention replies there.',
};

const MISSING_PREFIXES: Record<SignupReason, string> = {
  signup_disabled:
    'Start mention won\'t send: signup posts are off. Turn on "Post event signup embed" and pick a channel',
  signup_no_channel:
    "Start mention won't send: no signup channel is selected. Pick a signup channel",
};

export function startMentionPrerequisiteMessage(
  prerequisite: StartMentionPrerequisite,
): string | null {
  switch (prerequisite.kind) {
    case 'ok':
      return null;
    case 'announcement_fallback':
      return FALLBACK_MESSAGES[prerequisite.reason];
    case 'missing': {
      const alternative = prerequisite.announcementOn
        ? 'pick an announcement channel'
        : 'turn on the pre-day announcement with a channel';
      return `${MISSING_PREFIXES[prerequisite.reason]}, or ${alternative}.`;
    }
  }
}
