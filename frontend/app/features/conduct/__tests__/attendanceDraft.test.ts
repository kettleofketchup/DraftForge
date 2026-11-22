import { describe, expect, it } from 'vitest';
import {
  EMPTY_DRAFT,
  addWalkIn,
  attendanceRowKey,
  draftChanges,
  draftOutcome,
  isDirty,
  removeWalkIn,
  setOutcomes,
  type WalkIn,
} from '../attendanceDraft';
import { MEMBER, attendanceRow } from './fixtures';

const noOrgUser = attendanceRow({
  member: { ...MEMBER, org_user_pk: null, user_pk: 40, username: 'guest' },
  org_user_pk: null,
});

const stored = attendanceRow({
  member: { ...MEMBER, org_user_pk: 8, user_pk: 12, username: 'bob' },
  org_user_pk: 8,
  virtual: false,
});

function walkIn(user_pk: number): WalkIn {
  return { user_pk, username: `u${user_pk}`, nickname: null, avatarUrl: null };
}

describe('attendanceRowKey', () => {
  it('uses the org_user_pk when there is one', () => {
    expect(attendanceRowKey(attendanceRow())).toBe('7');
  });

  it('row key falls back to user-<pk> for a member without an OrgUser', () => {
    expect(attendanceRowKey(noOrgUser)).toBe('user-40');
  });
});

describe('setOutcomes', () => {
  it('bulk set skips keys no longer in rows', () => {
    const rows = [attendanceRow()];
    const draft = setOutcomes(
      EMPTY_DRAFT,
      rows,
      ['7', '99', 'user-5'],
      'no_show',
    );
    expect([...draft.outcomes.entries()]).toEqual([['7', 'no_show']]);
  });

  it('setting a staff-sourced row back to its saved outcome drops the change', () => {
    const row = {
      ...stored,
      outcome: 'no_show' as const,
      source: 'staff' as const,
    };
    const changed = setOutcomes(EMPTY_DRAFT, [row], ['8'], 'excused');
    expect(changed.outcomes.get('8')).toBe('excused');
    const reverted = setOutcomes(changed, [row], ['8'], 'no_show');
    expect(reverted.outcomes.has('8')).toBe(false);
    expect(isDirty(reverted, [row])).toBe(false);
  });

  it('a ready_check row set to its own outcome is still a change', () => {
    const row = {
      ...stored,
      outcome: 'attended' as const,
      source: 'ready_check' as const,
    };
    const draft = setOutcomes(EMPTY_DRAFT, [row], ['8'], 'attended');
    expect(draftChanges(draft, [row])).toEqual([
      { org_user_pk: 8, outcome: 'attended' },
    ]);
  });

  it('a virtual row set to attended is still a change', () => {
    const row = attendanceRow({ virtual: true, outcome: 'attended' });
    const draft = setOutcomes(EMPTY_DRAFT, [row], ['7'], 'attended');
    expect(isDirty(draft, [row])).toBe(true);
  });

  it('returns a new draft and leaves the old one untouched', () => {
    const rows = [attendanceRow()];
    const next = setOutcomes(EMPTY_DRAFT, rows, ['7'], 'excused');
    expect(next).not.toBe(EMPTY_DRAFT);
    expect(EMPTY_DRAFT.outcomes.size).toBe(0);
  });
});

describe('draftOutcome', () => {
  it('prefers the draft value, else the row outcome', () => {
    const row = attendanceRow({ outcome: 'pending' });
    expect(draftOutcome(EMPTY_DRAFT, row)).toBe('pending');
    const draft = setOutcomes(EMPTY_DRAFT, [row], ['7'], 'late_cancel');
    expect(draftOutcome(draft, row)).toBe('late_cancel');
  });
});

describe('draftChanges', () => {
  it('draftChanges sends user_pk for a null org_user_pk row', () => {
    const draft = setOutcomes(EMPTY_DRAFT, [noOrgUser], ['user-40'], 'no_show');
    expect(draftChanges(draft, [noOrgUser])).toEqual([
      { user_pk: 40, outcome: 'no_show' },
    ]);
  });

  it('draftChanges drops entries whose row disappeared after a refetch', () => {
    const rows = [attendanceRow(), stored];
    const draft = setOutcomes(EMPTY_DRAFT, rows, ['7', '8'], 'no_show');
    expect(draftChanges(draft, [stored])).toEqual([
      { org_user_pk: 8, outcome: 'no_show' },
    ]);
    expect(isDirty(draft, [])).toBe(false);
  });

  it('walk-ins become attended user_pk changes, are de-duplicated, and a walk-in who is now a row is not sent twice', () => {
    let draft = addWalkIn(EMPTY_DRAFT, walkIn(50));
    draft = addWalkIn(draft, walkIn(50));
    draft = addWalkIn(draft, walkIn(40));
    expect(draft.walkIns).toHaveLength(2);
    expect(draftChanges(draft, [])).toEqual([
      { user_pk: 50, outcome: 'attended' },
      { user_pk: 40, outcome: 'attended' },
    ]);
    expect(draftChanges(draft, [noOrgUser])).toEqual([
      { user_pk: 50, outcome: 'attended' },
    ]);
  });

  it('removeWalkIn drops the walk-in', () => {
    const draft = removeWalkIn(addWalkIn(EMPTY_DRAFT, walkIn(50)), 50);
    expect(draft.walkIns).toEqual([]);
    expect(isDirty(draft, [])).toBe(false);
  });
});
