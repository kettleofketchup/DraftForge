import type { ChatErrorCode } from '../types';

const CHAT_ERROR_TEXT: Record<ChatErrorCode, string> = {
  not_participant: 'Spectators can only read chat',
  ambiguous_team: "You're on both rosters — ask an admin",
  empty: 'Type a message first',
  too_long: 'Message is too long (500 characters max)',
  rate_limited: 'Slow down a moment',
  draft_closed: 'Draft finished — chat is read-only',
  draft_inactive: 'Suggestions are only available while drafting',
  hero_unavailable: 'That hero is no longer available',
  bad_request: 'Message could not be sent',
  unavailable: 'Chat is unavailable — message not sent',
};

export function chatErrorText(code: ChatErrorCode): string {
  return CHAT_ERROR_TEXT[code];
}
