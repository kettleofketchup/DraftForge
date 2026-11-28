import { describe, expect, it } from 'vitest';

import { STAFF_REASON_POLICIES, type StaffReasonPolicy } from '../schemas';
import {
  LEDGER_ACTION_FOR,
  PLACEMENT_ACTIONS,
  type StaffSignupAction,
  staffReasonMode,
} from '../staffReasonPolicy';

const ACTIONS: StaffSignupAction[] = [
  'admin_add',
  'approve',
  'reject',
  'confirm',
  'unconfirm',
  'cancel',
  'demote',
  'reinstate',
  'void_withdrawal',
];

const FROM_STATUSES = ['waitlisted', 'rsvp', 'pending'] as const;

// backend/events/ledger.py is_placement + require_staff_reason
function expected(
  policy: StaffReasonPolicy,
  action: StaffSignupAction,
  fromStatus: string,
): 'required' | 'optional' {
  if (policy === 'all_staff_changes') return 'required';
  if (policy === 'optional') return 'optional';
  const placement =
    ['admin_add', 'demote', 'reinstate', 'void_withdrawal'].includes(action) ||
    (action === 'approve' && fromStatus === 'waitlisted');
  return placement ? 'required' : 'optional';
}

const MATRIX = STAFF_REASON_POLICIES.flatMap((policy) =>
  ACTIONS.flatMap((action) =>
    FROM_STATUSES.map((fromStatus) => ({
      policy,
      action,
      fromStatus,
      mode: expected(policy, action, fromStatus),
    })),
  ),
);

describe('staffReasonMode', () => {
  it('mirrors the backend placement set', () => {
    expect([...PLACEMENT_ACTIONS].sort()).toEqual([
      'demoted',
      'reinstated',
      'staff_added',
      'swapped',
      'transferred_in',
      'transferred_out',
      'voided_withdrawal',
    ]);
  });

  it('maps each UI action to the ledger action it records', () => {
    expect(LEDGER_ACTION_FOR).toEqual({
      admin_add: 'staff_added',
      approve: 'approved',
      reject: 'rejected',
      confirm: 'confirmed',
      unconfirm: 'unconfirmed',
      cancel: 'withdrew',
      demote: 'demoted',
      reinstate: 'reinstated',
      void_withdrawal: 'voided_withdrawal',
    });
  });

  it.each(MATRIX)(
    '$policy / $action from $fromStatus is $mode for another member',
    ({ policy, action, fromStatus, mode }) => {
      expect(
        staffReasonMode(policy, action, { fromStatus, isSelf: false }),
      ).toBe(mode);
    },
  );

  it.each(MATRIX)(
    '$policy / $action from $fromStatus is optional on your own signup',
    ({ policy, action, fromStatus }) => {
      expect(
        staffReasonMode(policy, action, { fromStatus, isSelf: true }),
      ).toBe('optional');
    },
  );

  it.each(ACTIONS)('an unknown policy is optional for %s', (action) => {
    expect(
      staffReasonMode(undefined, action, {
        fromStatus: 'waitlisted',
        isSelf: false,
      }),
    ).toBe('optional');
  });

  it('void withdrawal needs a reason under placements', () => {
    expect(
      staffReasonMode('placements', 'void_withdrawal', {
        fromStatus: 'cancelled',
        isSelf: false,
      }),
    ).toBe('required');
  });

  it('approve without a known status is not a placement', () => {
    expect(staffReasonMode('placements', 'approve', { isSelf: false })).toBe(
      'optional',
    );
  });
});
