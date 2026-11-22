import type {
  AttendanceChange,
  AttendanceRow,
  StaffSettableOutcome,
} from './schemas';

export interface WalkIn {
  user_pk: number;
  username: string;
  nickname: string | null;
  avatarUrl: string | null;
}

export interface AttendanceDraft {
  outcomes: ReadonlyMap<string, StaffSettableOutcome>;
  walkIns: readonly WalkIn[];
}

export const EMPTY_DRAFT: AttendanceDraft = {
  outcomes: new Map(),
  walkIns: [],
};

export function attendanceRowKey(
  row: Pick<AttendanceRow, 'org_user_pk' | 'member'>,
): string {
  return row.org_user_pk != null
    ? String(row.org_user_pk)
    : `user-${row.member.user_pk}`;
}

function rowsByKey(rows: readonly AttendanceRow[]): Map<string, AttendanceRow> {
  return new Map(rows.map((row) => [attendanceRowKey(row), row]));
}

// Mirrors backend services._apply, which skips a staff row set to its own outcome.
function isNoOp(row: AttendanceRow, outcome: StaffSettableOutcome): boolean {
  return !row.virtual && row.source === 'staff' && row.outcome === outcome;
}

export function setOutcomes(
  draft: AttendanceDraft,
  rows: readonly AttendanceRow[],
  keys: Iterable<string>,
  outcome: StaffSettableOutcome,
): AttendanceDraft {
  const byKey = rowsByKey(rows);
  const outcomes = new Map(draft.outcomes);
  for (const key of keys) {
    const row = byKey.get(key);
    if (!row) continue;
    if (isNoOp(row, outcome)) outcomes.delete(key);
    else outcomes.set(key, outcome);
  }
  return { ...draft, outcomes };
}

export function addWalkIn(
  draft: AttendanceDraft,
  walkIn: WalkIn,
): AttendanceDraft {
  if (draft.walkIns.some((w) => w.user_pk === walkIn.user_pk)) return draft;
  return { ...draft, walkIns: [...draft.walkIns, walkIn] };
}

export function removeWalkIn(
  draft: AttendanceDraft,
  userPk: number,
): AttendanceDraft {
  return {
    ...draft,
    walkIns: draft.walkIns.filter((w) => w.user_pk !== userPk),
  };
}

export function draftOutcome(
  draft: AttendanceDraft,
  row: AttendanceRow,
): AttendanceRow['outcome'] {
  return draft.outcomes.get(attendanceRowKey(row)) ?? row.outcome;
}

export function draftChanges(
  draft: AttendanceDraft,
  rows: readonly AttendanceRow[],
): AttendanceChange[] {
  const byKey = rowsByKey(rows);
  const changes: AttendanceChange[] = [];
  for (const [key, outcome] of draft.outcomes) {
    const row = byKey.get(key);
    if (!row) continue;
    changes.push(
      row.org_user_pk != null
        ? { org_user_pk: row.org_user_pk, outcome }
        : { user_pk: row.member.user_pk, outcome },
    );
  }
  const rowUserPks = new Set(rows.map((row) => row.member.user_pk));
  for (const walkIn of draft.walkIns) {
    if (rowUserPks.has(walkIn.user_pk)) continue;
    changes.push({ user_pk: walkIn.user_pk, outcome: 'attended' });
  }
  return changes;
}

export function isDirty(
  draft: AttendanceDraft,
  rows: readonly AttendanceRow[],
): boolean {
  return draftChanges(draft, rows).length > 0;
}
