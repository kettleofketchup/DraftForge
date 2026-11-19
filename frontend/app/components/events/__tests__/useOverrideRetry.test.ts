// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react';
import { AxiosError, AxiosHeaders } from 'axios';
import { describe, expect, it, vi } from 'vitest';

import type {
  OverrideAcknowledgement,
  OverrideRequired,
} from '~/components/api/overridesAPI';
import { useOverrideRetry } from '../useOverrideRetry';

function axiosError(status: number, data: unknown): AxiosError {
  return new AxiosError('fail', 'ERR_BAD_REQUEST', undefined, undefined, {
    status,
    statusText: '',
    data,
    headers: {},
    config: { headers: new AxiosHeaders() },
  });
}

function overrideBody(codes: string[], blocked = false): OverrideRequired {
  return {
    code: 'override_required',
    blocked,
    violations: codes.map((code) => ({
      code,
      rule: 'staff-override',
      category: 'eligibility',
      message: code,
      blocking: blocked,
      params: {},
    })),
  };
}

describe('useOverrideRetry', () => {
  it('prompts on 409 and resends with acknowledged codes', async () => {
    const action = vi
      .fn<(ack: OverrideAcknowledgement) => Promise<string>>()
      .mockRejectedValueOnce(axiosError(409, overrideBody(['a'])))
      .mockResolvedValueOnce('done');
    const onSuccess = vi.fn();
    const { result } = renderHook(() =>
      useOverrideRetry(action, { onSuccess }),
    );

    await act(() => result.current.run());
    expect(action).toHaveBeenLastCalledWith({
      acknowledged_codes: [],
      reason: '',
    });
    expect(result.current.dialogProps.open).toBe(true);

    await act(() => result.current.dialogProps.onConfirm('why'));
    expect(action).toHaveBeenLastCalledWith({
      acknowledged_codes: ['a'],
      reason: 'why',
    });
    expect(onSuccess).toHaveBeenCalledWith('done');
    expect(result.current.dialogProps.open).toBe(false);
  });

  it('prompts again for a new violation and keeps earlier acknowledgements', async () => {
    const action = vi
      .fn<(ack: OverrideAcknowledgement) => Promise<string>>()
      .mockRejectedValueOnce(axiosError(409, overrideBody(['a'])))
      .mockRejectedValueOnce(axiosError(409, overrideBody(['b'])))
      .mockResolvedValueOnce('done');
    const { result } = renderHook(() => useOverrideRetry(action));

    await act(() => result.current.run());
    await act(() => result.current.dialogProps.onConfirm('why'));
    expect(result.current.dialogProps.override?.violations[0].code).toBe('b');

    await act(() => result.current.dialogProps.onConfirm('why'));
    expect(action).toHaveBeenLastCalledWith({
      acknowledged_codes: ['a', 'b'],
      reason: 'why',
    });
  });

  it('surfaces the 400 reason error in the dialog', async () => {
    const action = vi
      .fn<(ack: OverrideAcknowledgement) => Promise<string>>()
      .mockRejectedValueOnce(axiosError(409, overrideBody(['a'])))
      .mockRejectedValueOnce(
        axiosError(400, { code: 'override_reason_required' }),
      );
    const { result } = renderHook(() => useOverrideRetry(action));

    await act(() => result.current.run());
    await act(() => result.current.dialogProps.onConfirm('x'));
    expect(result.current.dialogProps.open).toBe(true);
    expect(result.current.dialogProps.reasonError).toMatch(/reason/);
  });

  it('never resends a blocked override', async () => {
    const action = vi
      .fn<(ack: OverrideAcknowledgement) => Promise<string>>()
      .mockRejectedValueOnce(axiosError(409, overrideBody(['a'], true)));
    const { result } = renderHook(() => useOverrideRetry(action));

    await act(() => result.current.run());
    await act(() => result.current.dialogProps.onConfirm('why'));
    expect(action).toHaveBeenCalledTimes(1);
  });

  it('passes other errors to onError and resets on close', async () => {
    const boom = new Error('boom');
    const action = vi
      .fn<(ack: OverrideAcknowledgement) => Promise<string>>()
      .mockRejectedValueOnce(axiosError(409, overrideBody(['a'])))
      .mockRejectedValueOnce(boom);
    const onError = vi.fn();
    const { result } = renderHook(() => useOverrideRetry(action, { onError }));

    await act(() => result.current.run());
    act(() => result.current.dialogProps.onOpenChange(false));
    expect(result.current.dialogProps.open).toBe(false);

    await act(() => result.current.run());
    expect(onError).toHaveBeenCalledWith(boom);
  });
});
