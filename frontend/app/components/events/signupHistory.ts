import type {
  SignupHistoryEntry,
  SignupLedgerAction,
  SignupSnapshot,
} from '~/components/events/schemas';
import { DisplayName } from '~/components/user/avatar';

export const SIGNUP_ACTION_LABELS: Record<SignupLedgerAction, string> = {
  backfilled: 'Starting record',
  signed_up: 'Signed up',
  resigned_up: 'Signed up again',
  switched_commitment: 'Changed commitment',
  approved: 'Approved',
  confirmed: 'Confirmed',
  unconfirmed: 'Unconfirmed',
  rejected: 'Rejected',
  withdrew: 'Withdrew',
  declined: 'Declined',
  waitlisted: 'Waitlisted',
  promoted: 'Promoted from waitlist',
  demoted: 'Moved to waitlist',
  reinstated: 'Reinstated',
  voided_withdrawal: 'Withdrawal voided',
  transferred_out: 'Transferred out',
  transferred_in: 'Transferred in',
  swapped: 'Swapped',
  staff_added: 'Added by staff',
  account_merged: 'Account merged',
  moved_event: 'Moved event',
  event_cancelled: 'Event cancelled',
};

const titleCase = (slug: string): string => {
  const words = slug.replace(/_/g, ' ').trim();
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : slug;
};

const isKnownAction = (action: string): action is SignupLedgerAction =>
  Object.prototype.hasOwnProperty.call(SIGNUP_ACTION_LABELS, action);

export function actionLabel(action: string): string {
  return isKnownAction(action)
    ? SIGNUP_ACTION_LABELS[action]
    : titleCase(action);
}

const TONE_SUCCESS = 'bg-success/20 text-success border-success/30';
const TONE_WARNING = 'bg-warning/20 text-warning border-warning/30';
const TONE_ERROR = 'bg-error/20 text-error border-error/30';
const TONE_INFO = 'bg-info/20 text-info border-info/30';

export const ACTION_TONE: Record<SignupLedgerAction, string> = {
  signed_up: TONE_SUCCESS,
  resigned_up: TONE_SUCCESS,
  approved: TONE_SUCCESS,
  confirmed: TONE_SUCCESS,
  promoted: TONE_SUCCESS,
  reinstated: TONE_SUCCESS,
  staff_added: TONE_SUCCESS,
  waitlisted: TONE_WARNING,
  demoted: TONE_WARNING,
  unconfirmed: TONE_WARNING,
  switched_commitment: TONE_WARNING,
  withdrew: TONE_ERROR,
  declined: TONE_ERROR,
  rejected: TONE_ERROR,
  event_cancelled: TONE_ERROR,
  backfilled: TONE_INFO,
  voided_withdrawal: TONE_INFO,
  transferred_out: TONE_INFO,
  transferred_in: TONE_INFO,
  swapped: TONE_INFO,
  account_merged: TONE_INFO,
  moved_event: TONE_INFO,
};

export function actionTone(action: string): string {
  return isKnownAction(action) ? ACTION_TONE[action] : TONE_INFO;
}

const MEANS_LABELS: Record<string, string> = {
  web: 'Web',
  discord_button: 'Discord button',
  discord_reaction: 'Discord reaction',
  system: 'System',
};

export function meansLabel(entry: SignupHistoryEntry): string {
  if (entry.actor.role === 'staff') return 'Staff';
  if (entry.actor.role === 'system') return 'System';
  return MEANS_LABELS[entry.means] ?? titleCase(entry.means);
}

export type DiffField =
  | 'status'
  | 'commitment'
  | 'waitlist_position'
  | 'line_seq'
  | 'signed_up_at';

export type DiffPart = {
  field: DiffField;
  from: string | number | null;
  to: string | number | null;
};

export type HistoryDiff = DiffPart[] | { unavailable: true } | { note: string };

export const MERGE_DUPLICATE_NOTE =
  'Duplicate sign-up from merged account discarded; kept current sign-up';

const CHANGE_FIELDS = [
  'status',
  'commitment',
  'waitlist_position',
  'line_seq',
] as const satisfies readonly (keyof SignupSnapshot & DiffField)[];

export function describeDiff(entry: SignupHistoryEntry): HistoryDiff {
  const { before, after } = entry;
  if (!after) return { unavailable: true };

  if (!before) {
    const parts: DiffPart[] = [
      { field: 'status', from: null, to: after.status },
      { field: 'commitment', from: null, to: after.commitment },
    ];
    if (after.waitlist_position != null) {
      parts.push({
        field: 'waitlist_position',
        from: null,
        to: after.waitlist_position,
      });
    }
    if (entry.action === 'backfilled' && after.signed_up_at) {
      parts.push({ field: 'signed_up_at', from: null, to: after.signed_up_at });
    }
    return parts;
  }

  if (entry.action === 'account_merged' && before.extra?.discarded_duplicate) {
    return { note: MERGE_DUPLICATE_NOTE };
  }

  return CHANGE_FIELDS.filter((f) => before[f] !== after[f]).map((field) => ({
    field,
    from: before[field],
    to: after[field],
  }));
}

const COMMITMENT_LABELS: Record<string, string> = {
  main: 'Main',
  maybe: 'Maybe',
};

const commitmentLabel = (v: string | number | null): string =>
  v == null ? '' : (COMMITMENT_LABELS[String(v)] ?? titleCase(String(v)));

const statusLabel = (v: string | number | null): string =>
  v == null ? '' : titleCase(String(v));

/** Plain-text form of one diff part; status parts are normally rendered as badges. */
export function diffPartText(
  part: DiffPart,
  action: string,
  eventTimezone?: string,
): string {
  const { from, to } = part;
  switch (part.field) {
    case 'status':
      return from == null
        ? statusLabel(to)
        : `${statusLabel(from)} → ${statusLabel(to)}`;
    case 'commitment':
      return from == null
        ? commitmentLabel(to)
        : `${commitmentLabel(from)} → ${commitmentLabel(to)}`;
    case 'waitlist_position':
      return to == null ? 'Left the waitlist' : `#${to} on the waitlist`;
    case 'line_seq':
      return action === 'resigned_up'
        ? 'Moved to the end of the line'
        : `Place in line ${from ?? '–'} → ${to ?? '–'}`;
    case 'signed_up_at':
      return to == null
        ? ''
        : `Signed up ${formatHistoryTime(String(to), eventTimezone).short}`;
  }
}

const SIGNUP_START_ACTIONS: ReadonlySet<string> = new Set([
  'signed_up',
  'staff_added',
  'resigned_up',
]);

/** Oldest entry that started a sign-up; entries are newest first. */
export function originalSignupId(entries: SignupHistoryEntry[]): number | null {
  for (let i = entries.length - 1; i >= 0; i--) {
    const e = entries[i];
    if (SIGNUP_START_ACTIONS.has(e.action)) return e.id;
    if (
      e.action === 'backfilled' &&
      e.after != null &&
      e.after.status !== 'cancelled'
    ) {
      return e.id;
    }
  }
  return null;
}

export function causePhrase(
  entry: SignupHistoryEntry,
  loadedById: Map<number, SignupHistoryEntry>,
): string | null {
  if (entry.action !== 'promoted') return null;
  const cause =
    entry.caused_by == null ? undefined : loadedById.get(entry.caused_by);
  if (!cause) return 'automatic';
  const name = DisplayName(cause.subject);
  switch (cause.action) {
    case 'withdrew':
      return `after ${name} withdrew`;
    case 'rejected':
      return `after ${name} was rejected`;
    case 'declined':
      return `after ${name} declined`;
    case 'switched_commitment':
      return `after ${name} went tentative`;
    default:
      return `after ${name}: ${actionLabel(cause.action)}`;
  }
}

export function extraNotes(entry: SignupHistoryEntry): string[] {
  const extra: Record<string, unknown> = {
    ...(entry.before?.extra ?? {}),
    ...(entry.after?.extra ?? {}),
  };
  const notes: string[] = [];
  if (extra.staff_power === true) notes.push('Staff override on own sign-up');
  if (typeof extra.mmr_override === 'number') {
    notes.push(`MMR set to ${extra.mmr_override}`);
  }
  if (extra.from_user_id != null) notes.push('Merged from another account');
  if (entry.action === 'moved_event' && extra.event_id != null) {
    notes.push('Moved between events');
  }
  return notes;
}

const SHORT_FORMAT: Intl.DateTimeFormatOptions = {
  month: 'short',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
};

const FULL_FORMAT: Intl.DateTimeFormatOptions = {
  dateStyle: 'medium',
  timeStyle: 'long',
};

function formatter(
  options: Intl.DateTimeFormatOptions,
  timeZone?: string,
): Intl.DateTimeFormat {
  if (timeZone) {
    try {
      return new Intl.DateTimeFormat(undefined, { ...options, timeZone });
    } catch {
      // Unknown zone: use the browser zone.
    }
  }
  return new Intl.DateTimeFormat(undefined, options);
}

export function formatHistoryTime(
  iso: string,
  eventTimezone?: string,
): { short: string; full: string } {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return { short: iso, full: iso };
  return {
    short: formatter(SHORT_FORMAT, eventTimezone).format(date),
    full: formatter(FULL_FORMAT, eventTimezone).format(date),
  };
}
