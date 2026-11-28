import type { EventSignupType } from './schemas';
import { EventState, SignupStatus } from './schemas';

export const SIGNUP_ACTIONS = [
  'approve',
  'reject',
  'confirm',
  'cancel',
  'unconfirm',
  'demote',
  'reinstate',
] as const;

export type SignupAction = (typeof SIGNUP_ACTIONS)[number];

export interface PendingSignupAction {
  action: SignupAction;
  id: number;
}

/**
 * The status the server will give a signup after `action`, or null when it
 * depends on server-side state (reinstate outside roll call can land on
 * approved, pending or waitlisted).
 */
export function optimisticSignupStatus(
  action: SignupAction,
  eventState: string | undefined,
): string | null {
  switch (action) {
    case 'approve':
    case 'unconfirm':
      return SignupStatus.APPROVED;
    case 'reject':
      return SignupStatus.REJECTED;
    case 'confirm':
      return SignupStatus.CONFIRMED;
    case 'cancel':
      return SignupStatus.CANCELLED;
    case 'demote':
      return SignupStatus.WAITLISTED;
    case 'reinstate':
      return eventState === EventState.ROLL_CALL ? SignupStatus.APPROVED : null;
  }
}

export function isSignupAction(value: unknown): value is SignupAction {
  return (SIGNUP_ACTIONS as readonly unknown[]).includes(value);
}

/** Signup id from mutation variables; null for `{ userId }` (admin add). */
export function signupIdOf(variables: unknown): number | null {
  if (typeof variables === 'number') return variables;
  if (
    variables &&
    typeof variables === 'object' &&
    'id' in variables &&
    typeof variables.id === 'number'
  )
    return variables.id;
  return null;
}

/**
 * Draw pending actions over the server list. Rows without a pending action
 * keep their object identity so memoised rows skip re-rendering. Later
 * actions in `pending` win over earlier ones for the same row.
 */
export function overlayPendingSignups(
  signups: EventSignupType[],
  pending: PendingSignupAction[],
  eventState: string | undefined,
): EventSignupType[] {
  if (pending.length === 0) return signups;
  const nextStatus = new Map<number, string>();
  for (const { action, id } of pending) {
    const status = optimisticSignupStatus(action, eventState);
    if (status) nextStatus.set(id, status);
  }
  if (nextStatus.size === 0) return signups;
  return signups.map((s) => {
    const status = nextStatus.get(s.id);
    return status && status !== s.status ? { ...s, status } : s;
  });
}

/** Swap one row for the server's copy, keeping every other row's identity. */
export function replaceSignup(
  signups: EventSignupType[],
  updated: EventSignupType,
): EventSignupType[] {
  const idx = signups.findIndex((s) => s.id === updated.id);
  if (idx === -1) return signups;
  const next = signups.slice();
  next[idx] = updated;
  return next;
}
