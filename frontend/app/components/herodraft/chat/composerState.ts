import type { ChatViewer } from '../types';
import { parseChatInput } from './parseChatInput';

const TERMINAL_STATES = new Set(['completed', 'abandoned']);

export interface ComposerState {
  inputDisabled: boolean;
  sendDisabled: boolean;
  placeholder: string;
}

export function composerState(a: {
  viewer: ChatViewer | null;
  draftState: string;
  connected: boolean;
  raw: string;
  unavailable?: boolean;
}): ComposerState {
  const { viewer, draftState, connected, raw, unavailable = false } = a;
  if (connected && viewer === null && unavailable) {
    return {
      inputDisabled: true,
      sendDisabled: true,
      placeholder: 'Chat unavailable',
    };
  }
  if (viewer === null || !connected) {
    return {
      inputDisabled: false,
      sendDisabled: true,
      placeholder: 'Connecting…',
    };
  }
  if (viewer.role === 'ambiguous') {
    return {
      inputDisabled: true,
      sendDisabled: true,
      placeholder: "You're on both rosters — ask an admin",
    };
  }
  if (!viewer.can_post_all) {
    return {
      inputDisabled: true,
      sendDisabled: true,
      placeholder: 'Spectators can read all chat',
    };
  }
  if (TERMINAL_STATES.has(draftState)) {
    return {
      inputDisabled: true,
      sendDisabled: true,
      placeholder: 'Draft finished — chat is read-only',
    };
  }
  return {
    inputDisabled: false,
    sendDisabled: parseChatInput(raw).body === '',
    placeholder: 'Team chat… (/all for everyone)',
  };
}
