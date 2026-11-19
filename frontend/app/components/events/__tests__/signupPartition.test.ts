import { describe, expect, it } from 'vitest';
import type { EventSignupType } from '../schemas';
import { partitionSignups } from '../signupPartition';

function row(
  id: number,
  status: string,
  holds_seat?: boolean,
): EventSignupType {
  const base = { id, status } as EventSignupType;
  return holds_seat === undefined ? base : { ...base, holds_seat };
}

describe('partitionSignups', () => {
  const signups = [
    row(1, 'rsvp', true),
    row(2, 'pending_approval', true),
    row(3, 'approved', true),
    row(4, 'confirmed', true),
    row(5, 'waitlisted', false),
    row(6, 'tentative', false),
    row(7, 'rejected', false),
    row(8, 'cancelled', false),
  ];

  it('puts exactly the seat-holders in active', () => {
    const { active } = partitionSignups(signups);
    expect(active.map((s) => s.id)).toEqual([1, 2, 3, 4]);
  });

  it('lets holds_seat, not the status, decide active', () => {
    const { active } = partitionSignups([row(9, 'rsvp', false)]);
    expect(active).toEqual([]);
  });

  it('treats a row without holds_seat as not active', () => {
    const { active } = partitionSignups([row(10, 'approved')]);
    expect(active).toEqual([]);
  });

  it('splits tentative and waitlisted by status', () => {
    const { tentative, waitlisted } = partitionSignups(signups);
    expect(tentative.map((s) => s.id)).toEqual([6]);
    expect(waitlisted.map((s) => s.id)).toEqual([5]);
  });
});
