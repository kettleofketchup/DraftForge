import type { EventSignupType } from './schemas';
import { SignupStatus } from './schemas';
import { canRestoreSignup } from './signupPartitions';

export interface RollCallRows {
  confirmed: EventSignupType[];
  awaiting: EventSignupType[];
  others: EventSignupType[];
  /** Every row in on-screen order: confirmed, awaiting, others. */
  ordered: EventSignupType[];
}

export type RollCallPrimaryAction = 'confirm' | 'approve' | 'restore';
export type RollCallRemoveAction = 'reject' | 'cancel';

export interface RollCallRowActions {
  primary: RollCallPrimaryAction | null;
  remove: RollCallRemoveAction | null;
}

const approvableStatuses: ReadonlySet<string> = new Set([
  SignupStatus.RSVP,
  SignupStatus.PENDING_APPROVAL,
  SignupStatus.WAITLISTED,
]);

export function isApprovableSignup(status: string): boolean {
  return approvableStatuses.has(status);
}

export function splitRollCallRows(signups: EventSignupType[]): RollCallRows {
  const confirmed: EventSignupType[] = [];
  const awaiting: EventSignupType[] = [];
  const others: EventSignupType[] = [];
  for (const signup of signups) {
    if (signup.status === SignupStatus.CONFIRMED) confirmed.push(signup);
    else if (signup.status === SignupStatus.APPROVED) awaiting.push(signup);
    else others.push(signup);
  }
  return {
    confirmed,
    awaiting,
    others,
    ordered: [...confirmed, ...awaiting, ...others],
  };
}

export function rollCallRowActions(status: string): RollCallRowActions {
  if (status === SignupStatus.APPROVED)
    return { primary: 'confirm', remove: 'reject' };
  if (status === SignupStatus.CONFIRMED)
    return { primary: null, remove: 'cancel' };
  if (isApprovableSignup(status))
    return { primary: 'approve', remove: 'reject' };
  if (canRestoreSignup(status)) return { primary: 'restore', remove: null };
  return { primary: null, remove: null };
}

/** The row the cursor lands on when nothing is selected: first awaiting, else first row. */
export function defaultRollCallFocus(rows: RollCallRows): number | null {
  return rows.awaiting[0]?.id ?? rows.ordered[0]?.id ?? null;
}

/** Resolve the selected row, falling back to the default when it has gone away. */
export function resolveRollCallFocus(
  rows: RollCallRows,
  focusedId: number | null,
): number | null {
  if (focusedId !== null && rows.ordered.some((s) => s.id === focusedId))
    return focusedId;
  return defaultRollCallFocus(rows);
}

export function moveRollCallFocus(
  rows: RollCallRows,
  focusedId: number | null,
  delta: number,
): number | null {
  const { ordered } = rows;
  if (ordered.length === 0) return null;
  const current = ordered.findIndex((s) => s.id === focusedId);
  if (current === -1) return defaultRollCallFocus(rows);
  const next = Math.min(Math.max(current + delta, 0), ordered.length - 1);
  return ordered[next].id;
}

function sectionOf(rows: RollCallRows, id: number): EventSignupType[] | null {
  for (const section of [rows.confirmed, rows.awaiting, rows.others]) {
    if (section.some((s) => s.id === id)) return section;
  }
  return null;
}

/**
 * Where the cursor goes once the acted-on row leaves its section: the next
 * row in that section, else the previous one, else the first other awaiting
 * row. Keeps an admin working down the awaiting list one key at a time.
 */
export function rollCallFocusAfterAction(
  rows: RollCallRows,
  actedId: number,
): number | null {
  const section = sectionOf(rows, actedId);
  if (section) {
    const idx = section.findIndex((s) => s.id === actedId);
    const neighbour = section[idx + 1] ?? section[idx - 1];
    if (neighbour) return neighbour.id;
  }
  const awaiting = rows.awaiting.find((s) => s.id !== actedId);
  if (awaiting) return awaiting.id;
  return rows.ordered.find((s) => s.id !== actedId)?.id ?? null;
}
