// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react';
import { AxiosError, AxiosHeaders } from 'axios';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { OverrideRequired } from '~/components/api/overridesAPI';
import type { useSignupActionMutations } from '~/hooks/useEvent';

const { toastError } = vi.hoisted(() => ({ toastError: vi.fn() }));
vi.mock('sonner', () => ({ toast: { error: toastError } }));

import { useSignupOverride } from '../useSignupOverride';

function axiosError(status: number, data: unknown): AxiosError {
  return new AxiosError('fail', 'ERR_BAD_REQUEST', undefined, undefined, {
    status,
    statusText: '',
    data,
    headers: {},
    config: { headers: new AxiosHeaders() },
  });
}

const overrideBody: OverrideRequired = {
  code: 'override_required',
  blocked: false,
  violations: [
    {
      code: 'not_org_member',
      rule: 'membership',
      category: 'eligibility',
      message: 'Not a member',
      blocking: false,
      params: {},
    },
  ],
};

function setup() {
  const mutations = {
    voidWithdrawal: { mutateAsync: vi.fn() },
    reinstate: { mutateAsync: vi.fn() },
    transfer: { mutateAsync: vi.fn() },
  };
  const hook = renderHook(() =>
    useSignupOverride(
      mutations as unknown as ReturnType<typeof useSignupActionMutations>,
    ),
  );
  return { mutations, hook };
}

describe('useSignupOverride transfer', () => {
  beforeEach(() => vi.clearAllMocks());

  it('retries a transfer after a 409 with the same recipient, acks and reason', async () => {
    const { mutations, hook } = setup();
    const transfer = mutations.transfer.mutateAsync;
    transfer
      .mockRejectedValueOnce(axiosError(409, overrideBody))
      .mockResolvedValueOnce({ mode: 'transfer' });

    await act(() =>
      hook.result.current.fire('transfer', 4, 'Sam', { recipientUserId: 9 })(
        'staff reason',
      ),
    );
    expect(transfer).toHaveBeenLastCalledWith({
      id: 4,
      recipient_user_id: 9,
      reason: 'staff reason',
    });
    expect(hook.result.current.dialogProps.open).toBe(true);
    expect(hook.result.current.dialogProps.subject).toBe(
      "transferring Sam's place",
    );
    expect(hook.result.current.dialogProps.defaultReason).toBe('staff reason');

    await act(() => hook.result.current.dialogProps.onConfirm('override why'));
    expect(transfer).toHaveBeenCalledTimes(2);
    expect(transfer).toHaveBeenLastCalledWith({
      id: 4,
      recipient_user_id: 9,
      reason: 'override why',
      acknowledged_codes: ['not_org_member'],
    });
    expect(hook.result.current.dialogProps.open).toBe(false);
    expect(mutations.reinstate.mutateAsync).not.toHaveBeenCalled();
    expect(mutations.voidWithdrawal.mutateAsync).not.toHaveBeenCalled();
  });

  it('toasts the transfer failure copy when a retry fails without a message', async () => {
    const { mutations, hook } = setup();
    mutations.transfer.mutateAsync
      .mockRejectedValueOnce(axiosError(409, overrideBody))
      .mockRejectedValueOnce(new Error());

    await act(() =>
      hook.result.current.fire('transfer', 4, undefined, {
        recipientUserId: 9,
      })(),
    );
    expect(hook.result.current.dialogProps.subject).toBeUndefined();
    await act(() => hook.result.current.dialogProps.onConfirm('why'));
    expect(toastError).toHaveBeenCalledWith('Failed to transfer place');
  });

  it('still routes restore and void through their own mutations', async () => {
    const { mutations, hook } = setup();
    mutations.reinstate.mutateAsync.mockResolvedValue({});
    mutations.voidWithdrawal.mutateAsync.mockResolvedValue({});

    await act(() => hook.result.current.fire('reinstate', 1)('r'));
    await act(() => hook.result.current.fire('void_withdrawal', 2)());
    expect(mutations.reinstate.mutateAsync).toHaveBeenCalledWith({
      id: 1,
      reason: 'r',
    });
    expect(mutations.voidWithdrawal.mutateAsync).toHaveBeenCalledWith({
      id: 2,
    });
    expect(mutations.transfer.mutateAsync).not.toHaveBeenCalled();
  });
});
