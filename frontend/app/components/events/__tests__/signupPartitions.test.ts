import { describe, expect, it } from 'vitest';
import type { EventSignupType } from '../schemas';
import { isRemovedSignup, partitionSignups } from '../signupPartitions';

function signup(id: number, status: string): EventSignupType {
  return { id, status } as unknown as EventSignupType;
}

describe('partitionSignups', () => {
  it('groups every status the way the event page does', () => {
    const rows = [
      signup(1, 'rsvp'),
      signup(2, 'pending_approval'),
      signup(3, 'approved'),
      signup(4, 'confirmed'),
      signup(5, 'tentative'),
      signup(6, 'waitlisted'),
      signup(7, 'cancelled'),
      signup(8, 'rejected'),
      signup(9, 'dropped'),
    ];
    const ids = (list: EventSignupType[]) => list.map((s) => s.id);
    const parts = partitionSignups(rows);
    expect(ids(parts.active)).toEqual([1, 2, 3, 4]);
    expect(ids(parts.tentative)).toEqual([5]);
    expect(ids(parts.waitlisted)).toEqual([6]);
    expect(ids(parts.removed)).toEqual([7, 8, 9]);
  });

  it('keeps tentative and waitlisted out of active', () => {
    const parts = partitionSignups([
      signup(1, 'tentative'),
      signup(2, 'waitlisted'),
    ]);
    expect(parts.active).toEqual([]);
  });

  it('returns empty groups for no signups', () => {
    expect(partitionSignups([])).toEqual({
      active: [],
      tentative: [],
      waitlisted: [],
      removed: [],
    });
  });
});

describe('isRemovedSignup', () => {
  it.each(['dropped', 'cancelled', 'rejected'])('%s is removed', (status) => {
    expect(isRemovedSignup(status)).toBe(true);
  });

  it.each(['rsvp', 'approved', 'confirmed', 'tentative', 'waitlisted'])(
    '%s is not removed',
    (status) => {
      expect(isRemovedSignup(status)).toBe(false);
    },
  );
});
