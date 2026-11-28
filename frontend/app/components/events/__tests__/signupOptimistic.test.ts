import { describe, expect, it } from 'vitest';
import type { EventSignupType } from '../schemas';
import {
  isSignupAction,
  optimisticSignupStatus,
  overlayPendingSignups,
  replaceSignup,
  SIGNUP_ACTIONS,
  signupIdOf,
  upsertSignup,
} from '../signupOptimistic';

function signup(id: number, status: string): EventSignupType {
  return { id, status } as unknown as EventSignupType;
}

describe('optimisticSignupStatus', () => {
  it.each([
    ['approve', 'approved'],
    ['unconfirm', 'approved'],
    ['reject', 'rejected'],
    ['confirm', 'confirmed'],
    ['cancel', 'cancelled'],
    ['demote', 'waitlisted'],
  ] as const)('%s → %s', (action, status) => {
    expect(optimisticSignupStatus(action, 'signups_open')).toBe(status);
  });

  it.each(['roll_call', 'signups_open', undefined])(
    'leaves reinstate and void_withdrawal to the server in %s',
    (state) => {
      expect(optimisticSignupStatus('reinstate', state)).toBeNull();
      expect(optimisticSignupStatus('void_withdrawal', state)).toBeNull();
    },
  );

  it('leaves transfer to the server', () => {
    expect(SIGNUP_ACTIONS).toContain('transfer');
    expect(isSignupAction('transfer')).toBe(true);
    expect(optimisticSignupStatus('transfer', 'signups_open')).toBeNull();
  });
});

describe('signupIdOf', () => {
  it('reads the giver id from transfer vars', () => {
    expect(signupIdOf({ id: 4, recipient_user_id: 9 })).toBe(4);
  });

  it('reads plain ids and { id } objects', () => {
    expect(signupIdOf(7)).toBe(7);
    expect(signupIdOf({ id: 8, mmr: 3000 })).toBe(8);
    expect(signupIdOf(undefined)).toBeNull();
    expect(signupIdOf({ mmr: 1 })).toBeNull();
  });
});

describe('overlayPendingSignups', () => {
  const list = [
    signup(1, 'approved'),
    signup(2, 'approved'),
    signup(3, 'rsvp'),
  ];

  it('returns the same array when nothing is pending', () => {
    expect(overlayPendingSignups(list, [], 'roll_call')).toBe(list);
  });

  it('changes only pending rows and keeps the rest by reference', () => {
    const out = overlayPendingSignups(
      list,
      [{ action: 'confirm', id: 1 }],
      'roll_call',
    );
    expect(out.map((s) => s.status)).toEqual(['confirmed', 'approved', 'rsvp']);
    expect(out[0]).not.toBe(list[0]);
    expect(out[1]).toBe(list[1]);
    expect(out[2]).toBe(list[2]);
    expect(list[0].status).toBe('approved');
  });

  it('lets the latest action on a row win', () => {
    const out = overlayPendingSignups(
      list,
      [
        { action: 'confirm', id: 2 },
        { action: 'cancel', id: 2 },
      ],
      'roll_call',
    );
    expect(out[1].status).toBe('cancelled');
  });

  it('leaves unpredictable actions to the server', () => {
    const out = overlayPendingSignups(
      [signup(4, 'cancelled')],
      [{ action: 'reinstate', id: 4 }],
      'signups_open',
    );
    expect(out[0].status).toBe('cancelled');
  });

  it('keeps a voided or restored row in place during roll call', () => {
    const rows = [signup(4, 'cancelled'), signup(5, 'rejected')];
    const out = overlayPendingSignups(
      rows,
      [
        { action: 'reinstate', id: 4 },
        { action: 'void_withdrawal', id: 5 },
      ],
      'roll_call',
    );
    expect(out).toBe(rows);
  });
});

describe('replaceSignup', () => {
  it('swaps one row and keeps the others', () => {
    const list = [signup(1, 'approved'), signup(2, 'approved')];
    const updated = signup(2, 'confirmed');
    const out = replaceSignup(list, updated);
    expect(out[1]).toBe(updated);
    expect(out[0]).toBe(list[0]);
    expect(out).not.toBe(list);
  });

  it('ignores rows that are not in the list', () => {
    const list = [signup(1, 'approved')];
    expect(replaceSignup(list, signup(9, 'confirmed'))).toBe(list);
  });
});

describe('upsertSignup', () => {
  it('replaces an existing row in place and keeps the others', () => {
    const list = [signup(1, 'approved'), signup(2, 'approved')];
    const updated = signup(1, 'cancelled');
    const out = upsertSignup(list, updated);
    expect(out).toEqual([updated, list[1]]);
    expect(out[1]).toBe(list[1]);
    expect(out).not.toBe(list);
  });

  it('appends a row that is not in the list', () => {
    const list = [signup(1, 'approved')];
    const added = signup(9, 'approved');
    const out = upsertSignup(list, added);
    expect(out).toEqual([list[0], added]);
    expect(out[0]).toBe(list[0]);
  });
});
