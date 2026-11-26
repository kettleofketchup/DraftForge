// Mirrors backend/events/discord/channels.py and tasks.py announcement_available.

export type ChannelPost = 'signup' | 'attendance' | 'profile' | 'newEvent';

export type PostChannelState =
  | { kind: 'own' }
  | { kind: 'fallback'; channelId: string }
  | { kind: 'none' };

export interface PostChannelValues {
  announcement: boolean | undefined;
  announcementChannelId: string | null | undefined;
  signupChannelId: string | null | undefined;
  attendanceChannelId: string | null | undefined;
  profileChannelId: string | null | undefined;
  newEventChannelId: string | null | undefined;
}

export const NO_CHANNEL_WARNING =
  "This post won't send: pick a channel here or set an announcement channel.";

export const SIGNUP_NO_CHANNEL_WARNING =
  "The signup embed won't post: pick a signup channel, or turn on the pre-day announcement and pick its channel.";

const OWN_CHANNEL: Record<ChannelPost, keyof PostChannelValues> = {
  signup: 'signupChannelId',
  attendance: 'attendanceChannelId',
  profile: 'profileChannelId',
  newEvent: 'newEventChannelId',
};

export function postChannelState(
  post: ChannelPost,
  values: PostChannelValues,
): PostChannelState {
  if (values[OWN_CHANNEL[post]]) return { kind: 'own' };
  const fallbackId = values.announcementChannelId;
  if (!fallbackId) return { kind: 'none' };
  if (post === 'signup' && !values.announcement) return { kind: 'none' };
  return { kind: 'fallback', channelId: fallbackId };
}
