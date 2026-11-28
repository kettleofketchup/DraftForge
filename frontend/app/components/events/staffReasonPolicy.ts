import type { StaffReasonPolicy } from './schemas';

export type StaffSignupAction =
  | 'admin_add'
  | 'approve'
  | 'reject'
  | 'confirm'
  | 'unconfirm'
  | 'cancel'
  | 'demote'
  | 'reinstate'
  | 'void_withdrawal';

export const LEDGER_ACTION_FOR: Record<StaffSignupAction, string> = {
  admin_add: 'staff_added',
  approve: 'approved',
  reject: 'rejected',
  confirm: 'confirmed',
  unconfirm: 'unconfirmed',
  cancel: 'withdrew',
  demote: 'demoted',
  reinstate: 'reinstated',
  void_withdrawal: 'voided_withdrawal',
};

// backend/events/ledger.py PLACEMENT_ACTIONS
export const PLACEMENT_ACTIONS: ReadonlySet<string> = new Set([
  'staff_added',
  'demoted',
  'reinstated',
  'voided_withdrawal',
  'transferred_out',
  'transferred_in',
  'swapped',
]);

export function staffReasonMode(
  policy: StaffReasonPolicy | undefined,
  action: StaffSignupAction,
  { fromStatus, isSelf }: { fromStatus?: string; isSelf: boolean },
): 'required' | 'optional' {
  if (isSelf) return 'optional';
  if (policy === 'all_staff_changes') return 'required';
  const ledgerAction = LEDGER_ACTION_FOR[action];
  const placement =
    PLACEMENT_ACTIONS.has(ledgerAction) ||
    (ledgerAction === 'approved' && fromStatus === 'waitlisted');
  return policy === 'placements' && placement ? 'required' : 'optional';
}
