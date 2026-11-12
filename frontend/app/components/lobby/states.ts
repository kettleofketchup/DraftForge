// Display labels and colours for lobby states, shared by the match modal
// and the bracket node dot.

const LABELS: Record<string, string> = {
  requested: 'Requested',
  error: 'Error',
  pending: 'Pending',
  creating: 'Creating',
  waiting: 'Waiting for players',
  ready: 'Ready',
  launching: 'Launching',
  in_game: 'In game',
  post_game: 'Post game',
  finished: 'Finished',
  failed: 'Failed',
  closing: 'Closing',
  closed: 'Closed',
  timed_out: 'Timed out',
};

export function lobbyStateLabel(state: string): string {
  return LABELS[state] ?? state;
}

type Tone = 'pending' | 'open' | 'live' | 'problem' | 'done';

const TONES: Record<string, Tone> = {
  requested: 'pending',
  pending: 'pending',
  creating: 'pending',
  waiting: 'open',
  ready: 'open',
  launching: 'live',
  in_game: 'live',
  post_game: 'live',
  error: 'problem',
  failed: 'problem',
  timed_out: 'problem',
  finished: 'done',
  closing: 'done',
  closed: 'done',
};

export function lobbyStateToneName(state: string): Tone {
  return TONES[state] ?? 'pending';
}

// One colour per tone, from the theme's status colours: amber while the
// lobby waits for players, green while the match is on, red when staff need
// to act.
const BADGE_CLASSES: Record<Tone, string> = {
  pending: 'bg-muted text-muted-foreground',
  open: 'bg-warning/20 text-warning',
  live: 'bg-success/20 text-success',
  problem: 'bg-destructive/20 text-destructive',
  done: 'bg-muted text-muted-foreground',
};

// The bracket node dot. The foreground ring keeps it readable on every node
// header, including the red-tinted losers bracket; the live dot also pulses.
const DOT_CLASSES: Record<Tone, string> = {
  pending: 'bg-muted-foreground',
  open: 'bg-warning',
  live: 'bg-success motion-safe:animate-pulse',
  problem: 'bg-destructive',
  done: 'bg-muted-foreground/50',
};

export const LOBBY_DOT_BASE =
  'inline-block size-2.5 shrink-0 rounded-full ring-1 ring-foreground/80';

export function lobbyStateTone(state: string): string {
  return BADGE_CLASSES[lobbyStateToneName(state)];
}

export function lobbyStateDot(state: string): string {
  return DOT_CLASSES[lobbyStateToneName(state)];
}

/** Whether the bracket node shows a dot: not for lobbies that simply ended. */
export function showLobbyDot(state: string | null | undefined): state is string {
  return !!state && lobbyStateToneName(state) !== 'done';
}
