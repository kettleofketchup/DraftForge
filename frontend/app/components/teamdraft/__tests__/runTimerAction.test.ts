import { beforeEach, describe, expect, it, vi } from 'vitest';

const toast = vi.hoisted(() => ({ promise: vi.fn(), error: vi.fn() }));
vi.mock('sonner', () => ({ toast }));

import { runTimerAction } from '../timer/runTimerAction';

const rejected = () => Promise.reject({ response: { status: 409, data: { code: 'wrong_state' } } });

describe('runTimerAction', () => {
  beforeEach(() => {
    toast.promise.mockReset();
    toast.error.mockReset();
  });

  it('resolves with the action result', async () => {
    await expect(runTimerAction(() => Promise.resolve(5), 'Failed')).resolves.toBe(5);
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('never rejects and toasts the mapped error once', async () => {
    await expect(runTimerAction(rejected, 'Failed to pause')).resolves.toBeUndefined();
    expect(toast.error).toHaveBeenCalledTimes(1);
    expect(toast.error).toHaveBeenCalledWith('Draft is not in the right state for that');
  });

  it('leaves the error toast to toast.promise when progress messages are given', async () => {
    await expect(
      runTimerAction(rejected, 'Failed to pause', { loading: 'Pausing…', success: 'Draft paused' }),
    ).resolves.toBeUndefined();
    expect(toast.promise).toHaveBeenCalledTimes(1);
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('catches an action that throws synchronously', async () => {
    const boom = (): Promise<never> => {
      throw new Error('boom');
    };
    await expect(runTimerAction(boom, 'Failed')).resolves.toBeUndefined();
    expect(toast.error).toHaveBeenCalledWith('Failed');
  });
});
