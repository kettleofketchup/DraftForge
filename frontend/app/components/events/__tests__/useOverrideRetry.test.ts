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
    expect(action).toHaveBeenLastCalledWith({ acknowledged_codes: [] });
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

  it('keeps the caller reason on the first attempt, dialog reason on retry', async () => {
    const send = vi.fn<(body: Record<string, unknown>) => Promise<string>>();
    send
      .mockRejectedValueOnce(axiosError(409, overrideBody(['a'])))
      .mockResolvedValueOnce('done');
    const { result } = renderHook(() =>
      useOverrideRetry((ack) => send({ reason: 'caller', ...ack })),
    );

    await act(() => result.current.run());
    expect(send).toHaveBeenLastCalledWith({
      reason: 'caller',
      acknowledged_codes: [],
    });

    await act(() => result.current.dialogProps.onConfirm('dialog'));
    expect(send).toHaveBeenLastCalledWith({
      reason: 'dialog',
      acknowledged_codes: ['a'],
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

  it('passes the run ctx to the action', async () => {
    const action = vi
      .fn<
        (ack: OverrideAcknowledgement, ctx: { id: number }) => Promise<string>
      >()
      .mockResolvedValueOnce('done');
    const { result } = renderHook(() => useOverrideRetry(action));

    await act(() => result.current.run({ id: 1 }));
    expect(action).toHaveBeenCalledWith({ acknowledged_codes: [] }, { id: 1 });
  });

  it('retries on confirm with the stored ctx', async () => {
    const action = vi
      .fn<
        (ack: OverrideAcknowledgement, ctx: { id: number }) => Promise<string>
      >()
      .mockRejectedValueOnce(axiosError(409, overrideBody(['a'])))
      .mockResolvedValueOnce('done');
    const { result } = renderHook(() => useOverrideRetry(action));

    await act(() => result.current.run({ id: 1 }));
    await act(() => result.current.dialogProps.onConfirm('why'));
    expect(action).toHaveBeenLastCalledWith(
      { acknowledged_codes: ['a'], reason: 'why' },
      { id: 1 },
    );
  });

  it("resolves run with 'override' on 409 and 'done' on success", async () => {
    const action = vi
      .fn<(ack: OverrideAcknowledgement) => Promise<string>>()
      .mockRejectedValueOnce(axiosError(409, overrideBody(['a'])))
      .mockResolvedValueOnce('ok');
    const { result } = renderHook(() => useOverrideRetry(action));

    let outcome: string | undefined;
    await act(async () => {
      outcome = await result.current.run();
    });
    expect(outcome).toBe('override');

    act(() => result.current.dialogProps.onOpenChange(false));
    await act(async () => {
      outcome = await result.current.run();
    });
    expect(outcome).toBe('done');
  });

  it("resolves run with 'override' on a blocked 409", async () => {
    const action = vi
      .fn<(ack: OverrideAcknowledgement) => Promise<string>>()
      .mockRejectedValueOnce(axiosError(409, overrideBody(['a'], true)));
    const { result } = renderHook(() => useOverrideRetry(action));

    let outcome: string | undefined;
    await act(async () => {
      outcome = await result.current.run();
    });
    expect(outcome).toBe('override');
    expect(result.current.dialogProps.override?.blocked).toBe(true);
  });

  it('rethrow rejects run and skips onError', async () => {
    const err = axiosError(400, { code: 'reason_required' });
    const action = vi
      .fn<(ack: OverrideAcknowledgement) => Promise<string>>()
      .mockRejectedValueOnce(err);
    const onError = vi.fn();
    const { result } = renderHook(() =>
      useOverrideRetry(action, { onError, rethrow: true }),
    );

    let caught: unknown;
    await act(async () => {
      try {
        await result.current.run();
      } catch (e) {
        caught = e;
      }
    });
    expect(caught).toBe(err);
    expect(onError).not.toHaveBeenCalled();
    expect(result.current.pending).toBe(false);
  });

  it('errors after confirm still go to onError with rethrow', async () => {
    const boom = axiosError(500, {});
    const action = vi
      .fn<(ack: OverrideAcknowledgement) => Promise<string>>()
      .mockRejectedValueOnce(axiosError(409, overrideBody(['a'])))
      .mockRejectedValueOnce(boom);
    const onError = vi.fn();
    const { result } = renderHook(() =>
      useOverrideRetry(action, { onError, rethrow: true }),
    );

    await act(() => result.current.run());
    await act(() => result.current.dialogProps.onConfirm('why'));
    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError).toHaveBeenCalledWith(boom);
  });
});
