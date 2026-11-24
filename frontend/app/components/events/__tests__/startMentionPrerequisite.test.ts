import { describe, expect, it } from 'vitest';

import {
  START_MENTION_PREREQUISITE_NOTE,
  startMentionPrerequisite,
  startMentionPrerequisiteMessage,
  type StartMentionPrerequisite,
  type StartMentionPrerequisiteInput,
} from '../startMentionPrerequisite';

const row = (
  postSignups: boolean | undefined,
  signupChannelId: string | null | undefined,
  announcement: boolean | undefined,
  announcementChannelId: string | null | undefined,
  expected: StartMentionPrerequisite,
): [StartMentionPrerequisiteInput, StartMentionPrerequisite] => [
  { postSignups, signupChannelId, announcement, announcementChannelId },
  expected,
];

describe('startMentionPrerequisite', () => {
  it.each([
    row(true, '1', false, '', { kind: 'ok' }),
    row(true, '1', true, '2', { kind: 'ok' }),
    row(false, '', true, '2', {
      kind: 'announcement_fallback',
      reason: 'signup_disabled',
    }),
    row(false, '1', true, '2', {
      kind: 'announcement_fallback',
      reason: 'signup_disabled',
    }),
    row(true, '', true, '2', {
      kind: 'announcement_fallback',
      reason: 'signup_no_channel',
    }),
    row(false, '', false, '', {
      kind: 'missing',
      reason: 'signup_disabled',
      announcementOn: false,
    }),
    row(false, '1', false, '', {
      kind: 'missing',
      reason: 'signup_disabled',
      announcementOn: false,
    }),
    row(true, '', false, '', {
      kind: 'missing',
      reason: 'signup_no_channel',
      announcementOn: false,
    }),
    row(true, null, false, null, {
      kind: 'missing',
      reason: 'signup_no_channel',
      announcementOn: false,
    }),
    row(false, '', true, '', {
      kind: 'missing',
      reason: 'signup_disabled',
      announcementOn: true,
    }),
    row(undefined, undefined, undefined, undefined, {
      kind: 'missing',
      reason: 'signup_disabled',
      announcementOn: false,
    }),
  ])('%o -> %o', (input, expected) => {
    expect(startMentionPrerequisite(input)).toEqual(expected);
  });
});

describe('startMentionPrerequisiteMessage', () => {
  it.each<[StartMentionPrerequisite, string | null]>([
    [{ kind: 'ok' }, null],
    [
      { kind: 'announcement_fallback', reason: 'signup_disabled' },
      'Signup posts are off, so the signup embed is posted in the announcement channel and the mention replies there.',
    ],
    [
      { kind: 'announcement_fallback', reason: 'signup_no_channel' },
      'No signup channel is selected, so the signup embed is posted in the announcement channel and the mention replies there.',
    ],
    [
      { kind: 'missing', reason: 'signup_disabled', announcementOn: false },
      'Start mention won\'t send: signup posts are off. Turn on "Post event signup embed" below and pick a channel, or turn on the pre-day announcement with a channel.',
    ],
    [
      { kind: 'missing', reason: 'signup_disabled', announcementOn: true },
      'Start mention won\'t send: signup posts are off. Turn on "Post event signup embed" below and pick a channel, or pick an announcement channel.',
    ],
    [
      { kind: 'missing', reason: 'signup_no_channel', announcementOn: false },
      "Start mention won't send: no signup channel is selected. Pick a signup channel below, or turn on the pre-day announcement with a channel.",
    ],
    [
      { kind: 'missing', reason: 'signup_no_channel', announcementOn: true },
      "Start mention won't send: no signup channel is selected. Pick a signup channel below, or pick an announcement channel.",
    ],
  ])('%o', (prerequisite, expected) => {
    expect(startMentionPrerequisiteMessage(prerequisite)).toBe(expected);
  });

  it('pins the static prerequisite note', () => {
    expect(START_MENTION_PREREQUISITE_NOTE).toBe(
      "Replies to the event's signup post, which must already be posted when the mention is due. If it isn't posted yet, the mention is retried until roll call ends and may go out late or not at all.",
    );
  });
});
