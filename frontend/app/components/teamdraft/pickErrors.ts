export interface PickErrorInfo {
  message: string;
  jumpToPickNumber: number | null;
}

interface ErrorBody {
  code?: string;
  active_pick_number?: number | null;
  state?: string;
  error?: unknown;
  detail?: unknown;
}

const responseOf = (err: unknown): { status?: number; data?: unknown } | undefined =>
  (err as { response?: { status?: number; data?: unknown } } | null)?.response;

const bodyOf = (err: unknown): ErrorBody => {
  const data = responseOf(err)?.data;
  return data !== null && typeof data === 'object' ? (data as ErrorBody) : {};
};

export function describePickError(err: unknown): PickErrorInfo {
  const body = bodyOf(err);
  switch (body.code) {
    case 'not_active_round': {
      const n = body.active_pick_number;
      if (typeof n === 'number') {
        return {
          message: `That pick is no longer active — jumping to #${n}`,
          jumpToPickNumber: n,
        };
      }
      return { message: 'That pick is no longer active', jumpToPickNumber: null };
    }
    case 'draft_not_accepting_picks':
      return {
        message: `The draft is not accepting picks right now (${body.state ?? 'unknown'})`,
        jumpToPickNumber: null,
      };
    case 'paused_staff_only':
      return { message: 'Draft is paused — only staff can pick', jumpToPickNumber: null };
    case 'already_picked':
      return { message: 'That pick was already made', jumpToPickNumber: null };
  }
  return {
    message: `Failed to update captains: ${serverMessage(err)}`,
    jumpToPickNumber: null,
  };
}

function serverMessage(err: unknown): string {
  const response = responseOf(err);
  if (typeof response?.data === 'string' && response.data) return response.data;
  const body = bodyOf(err);
  for (const text of [body.error, body.detail]) {
    if (typeof text === 'string' && text) return text;
  }
  if (response?.status) return `request failed (${response.status})`;
  const message = (err as { message?: unknown } | null)?.message;
  return typeof message === 'string' && message ? message : 'unknown error';
}

export function handlePickError(
  err: unknown,
  deps: { jumpToPickNumber: (n: number) => boolean; refresh: () => void },
): string {
  const info = describePickError(err);
  if (info.jumpToPickNumber !== null && !deps.jumpToPickNumber(info.jumpToPickNumber)) {
    deps.refresh();
  }
  return info.message;
}

const TIMER_ACTION_MESSAGES: Record<string, string> = {
  wrong_state: 'Draft is not in the right state for that',
  timer_disabled: 'The pick clock is disabled for this tournament',
  clock_not_running: 'The clock is not running',
  already_armed: 'The clock is already running',
};

export function describeTimerActionError(err: unknown, fallback: string): string {
  const code = bodyOf(err).code;
  return (code && TIMER_ACTION_MESSAGES[code]) || fallback;
}
