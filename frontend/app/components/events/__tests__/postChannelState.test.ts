import { describe, expect, it } from 'vitest';

import {
  NO_CHANNEL_WARNING,
  SIGNUP_NO_CHANNEL_WARNING,
  postChannelState,
  type ChannelPost,
  type PostChannelValues,
} from '../postChannelState';

const blank: PostChannelValues = {
  announcement: true,
  announcementChannelId: '',
  signupChannelId: '',
  attendanceChannelId: '',
  profileChannelId: '',
  newEventChannelId: '',
};

const OWN_KEY: Record<ChannelPost, keyof PostChannelValues> = {
  signup: 'signupChannelId',
  attendance: 'attendanceChannelId',
  profile: 'profileChannelId',
  newEvent: 'newEventChannelId',
};

const POSTS: ChannelPost[] = ['signup', 'attendance', 'profile', 'newEvent'];

describe('postChannelState', () => {
  describe.each(POSTS)('%s', (post) => {
    it('is own when its channel is set', () => {
      expect(
        postChannelState(post, {
          ...blank,
          announcementChannelId: '222',
          [OWN_KEY[post]]: '111',
        }),
      ).toEqual({ kind: 'own' });
    });

    it('falls back to the announcement channel when blank', () => {
      expect(
        postChannelState(post, { ...blank, announcementChannelId: '222' }),
      ).toEqual({ kind: 'fallback', channelId: '222' });
    });

    it('is none when both channels are blank', () => {
      expect(postChannelState(post, blank)).toEqual({ kind: 'none' });
    });

    it('treats null and undefined ids as blank', () => {
      expect(
        postChannelState(post, {
          ...blank,
          announcementChannelId: null,
          [OWN_KEY[post]]: undefined,
        }),
      ).toEqual({ kind: 'none' });
    });
  });

  it('signup does not fall back while the announcement toggle is off', () => {
    expect(
      postChannelState('signup', {
        ...blank,
        announcement: false,
        announcementChannelId: '222',
      }),
    ).toEqual({ kind: 'none' });
  });

  it.each<ChannelPost>(['attendance', 'profile', 'newEvent'])(
    '%s falls back with the announcement toggle off',
    (post) => {
      expect(
        postChannelState(post, {
          ...blank,
          announcement: false,
          announcementChannelId: '222',
        }),
      ).toEqual({ kind: 'fallback', channelId: '222' });
    },
  );

  it('exports the warning copy', () => {
    expect(NO_CHANNEL_WARNING).toBe(
      "This post won't send: pick a channel here or set an announcement channel.",
    );
    expect(SIGNUP_NO_CHANNEL_WARNING).toBe(
      "The signup embed won't post: pick a signup channel, or turn on the pre-day announcement and pick its channel.",
    );
  });
});
