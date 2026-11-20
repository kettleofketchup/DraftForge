import type {
  ChatErrorCode,
  ChatMessage,
  ChatViewer,
  PendingChat,
} from '../types';

export const CHAT_MESSAGE_CAP = 200;

export interface ChatState {
  messages: ChatMessage[];
  viewer: ChatViewer | null;
  pending: Record<string, PendingChat>;
  lastError: { code: ChatErrorCode; text?: string } | null;
  unread: number;
  panelOpen: boolean;
}

export const initialChatState: ChatState = {
  messages: [],
  viewer: null,
  pending: {},
  lastError: null,
  unread: 0,
  panelOpen: false,
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

export function applyChatHistory(
  s: ChatState,
  viewer: ChatViewer,
  messages: ChatMessage[],
): ChatState {
  const unique = new Map(messages.map((m) => [m.id, m]));
  return {
    ...s,
    viewer,
    messages: capNewest([...unique.values()].sort(compareMessages)),
  };
}

export function applyChatMessage(s: ChatState, m: ChatMessage): ChatState {
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
    unread: s.panelOpen ? s.unread : s.unread + 1,
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
): ChatState {
  const failed = clientMsgId !== undefined ? s.pending[clientMsgId] : undefined;
  return {
    ...s,
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
  return {
    ...initialChatState,
    panelOpen: s.panelOpen,
    lastError: latest ? { code: 'unavailable', text: latest.raw } : null,
  };
}
