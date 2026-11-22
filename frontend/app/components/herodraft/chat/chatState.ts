import type {
  ChatErrorCode,
  ChatMessage,
  ChatViewer,
  PendingChat,
} from '../types';
import { isWithdrawal } from './suggestions';

export const CHAT_MESSAGE_CAP = 200;

export interface ChatState {
  messages: ChatMessage[];
  viewer: ChatViewer | null;
  pending: Record<string, PendingChat>;
  lastError: { code: ChatErrorCode; text?: string } | null;
  unread: number;
  panelOpen: boolean;
  /** The server could not start chat for this socket. */
  unavailable: boolean;
  /** Newest message seen before a disconnect; `{ after: null }` means none. */
  resyncAfter: { after: ChatMessage | null } | null;
  /** Latest message pushed live (never from history); a new object each time. */
  live: { message: ChatMessage } | null;
}

export const initialChatState: ChatState = {
  messages: [],
  viewer: null,
  pending: {},
  lastError: null,
  unread: 0,
  panelOpen: false,
  unavailable: false,
  resyncAfter: null,
  live: null,
};

function compareMessages(a: ChatMessage, b: ChatMessage): number {
  if (a.created_at !== b.created_at)
    return a.created_at < b.created_at ? -1 : 1;
  if (a.id === b.id) return 0;
  return a.id < b.id ? -1 : 1;
}

function capNewest(messages: ChatMessage[]): ChatMessage[] {
  return messages.length > CHAT_MESSAGE_CAP
    ? messages.slice(messages.length - CHAT_MESSAGE_CAP)
    : messages;
}

function withoutPending(
  pending: Record<string, PendingChat>,
  clientMsgId: string,
): Record<string, PendingChat> {
  const { [clientMsgId]: _removed, ...rest } = pending;
  return rest;
}

const countsAsUnread = (m: ChatMessage, selfId?: number): boolean =>
  (selfId === undefined || m.sender.pk !== selfId) && !isWithdrawal(m.kind);

export function applyChatHistory(
  s: ChatState,
  viewer: ChatViewer,
  messages: ChatMessage[],
  selfId?: number,
): ChatState {
  const unique = new Map(messages.map((m) => [m.id, m]));
  const sorted = capNewest([...unique.values()].sort(compareMessages));
  const mark = s.resyncAfter;
  const missed =
    mark === null || s.panelOpen
      ? 0
      : sorted.filter(
          (m) =>
            countsAsUnread(m, selfId) &&
            (mark.after === null || compareMessages(m, mark.after) > 0),
        ).length;
  return {
    ...s,
    viewer,
    messages: sorted,
    unread: s.unread + missed,
    unavailable: false,
    resyncAfter: null,
  };
}

export function applyChatMessage(
  s: ChatState,
  m: ChatMessage,
  selfId?: number,
): ChatState {
  if (s.messages.some((existing) => existing.id === m.id)) return s;
  let index = s.messages.length;
  while (index > 0 && compareMessages(s.messages[index - 1], m) > 0) index -= 1;
  const messages = [
    ...s.messages.slice(0, index),
    m,
    ...s.messages.slice(index),
  ];
  const capped = capNewest(messages);
  if (!capped.includes(m)) return s;
  return {
    ...s,
    messages: capped,
    live: { message: m },
    unread: s.panelOpen || !countsAsUnread(m, selfId) ? s.unread : s.unread + 1,
  };
}

export function applyChatAck(s: ChatState, clientMsgId: string): ChatState {
  if (!(clientMsgId in s.pending)) return s;
  return { ...s, pending: withoutPending(s.pending, clientMsgId) };
}

export function applyChatError(
  s: ChatState,
  code: ChatErrorCode,
  clientMsgId?: string,
  viewer?: ChatViewer,
): ChatState {
  if (clientMsgId === undefined && code === 'unavailable' && !s.viewer) {
    return { ...s, unavailable: true };
  }
  const failed = clientMsgId !== undefined ? s.pending[clientMsgId] : undefined;
  return {
    ...s,
    viewer: viewer ?? s.viewer,
    pending:
      failed && clientMsgId !== undefined
        ? withoutPending(s.pending, clientMsgId)
        : s.pending,
    lastError: failed ? { code, text: failed.raw } : { code },
  };
}

export function addPending(s: ChatState, p: PendingChat): ChatState {
  return { ...s, pending: { ...s.pending, [p.clientMsgId]: p } };
}

export function resetChatOnDisconnect(s: ChatState): ChatState {
  const latest = Object.values(s.pending).reduce<PendingChat | null>(
    (acc, p) => (acc === null || p.sentAt >= acc.sentAt ? p : acc),
    null,
  );
  const resyncAfter =
    s.viewer === null ? s.resyncAfter : { after: s.messages.at(-1) ?? null };
  return {
    ...initialChatState,
    panelOpen: s.panelOpen,
    unread: s.unread,
    resyncAfter,
    lastError: latest ? { code: 'unavailable', text: latest.raw } : null,
  };
}
