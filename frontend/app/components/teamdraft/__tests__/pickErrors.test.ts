import { describe, expect, it, vi } from 'vitest';
import {
  describePickError,
  describeTimerActionError,
  handlePickError,
} from '~/components/teamdraft/pickErrors';
const axiosErr = (status: number, data: unknown) => ({ response: { status, data } });
it('maps not_active_round to a jump', () => expect(describePickError(axiosErr(409, { code: 'not_active_round', active_pick_number: 5 }))).toEqual({ message: 'That pick is no longer active — jumping to #5', jumpToPickNumber: 5 }));
it('maps paused_staff_only, draft_not_accepting_picks and already_picked without a jump', () => {
  expect(describePickError(axiosErr(403, { code: 'paused_staff_only' })).jumpToPickNumber).toBeNull();
  expect(describePickError(axiosErr(409, { code: 'draft_not_accepting_picks', state: 'pending' })).message).toContain('pending');
  expect(describePickError(axiosErr(409, { code: 'already_picked' })).message).toBe('That pick was already made');
});
it('falls back to the legacy message for unknown errors', () => expect(describePickError(axiosErr(500, 'boom')).message).toBe('Failed to update captains: boom'));
it('describeTimerActionError maps the four codes and falls back', () => {
  expect(describeTimerActionError(axiosErr(400, { code: 'timer_disabled' }), 'x')).toBe('The pick clock is disabled for this tournament');
  expect(describeTimerActionError(axiosErr(409, { code: 'already_armed' }), 'x')).toBe('The clock is already running');
  expect(describeTimerActionError(new Error('net'), 'Failed to pause')).toBe('Failed to pause');
});
const notActive = axiosErr(409, { code: 'not_active_round', active_pick_number: 7 });
it('handlePickError does not refresh when the jump hits', () => {
  const jump = vi.fn(() => true);
  const refresh = vi.fn();
  expect(handlePickError(notActive, { jumpToPickNumber: jump, refresh })).toBe('That pick is no longer active — jumping to #7');
  expect(jump).toHaveBeenCalledWith(7);
  expect(refresh).not.toHaveBeenCalled();
});
it('handlePickError refreshes once when the jump misses', () => {
  const refresh = vi.fn();
  handlePickError(notActive, { jumpToPickNumber: () => false, refresh });
  expect(refresh).toHaveBeenCalledTimes(1);
});
it('handlePickError neither jumps nor refreshes for unknown errors', () => {
  const jump = vi.fn(() => false);
  const refresh = vi.fn();
  expect(handlePickError(axiosErr(500, 'boom'), { jumpToPickNumber: jump, refresh })).toBe('Failed to update captains: boom');
  expect(jump).not.toHaveBeenCalled();
  expect(refresh).not.toHaveBeenCalled();
});

describe('server error messages are shown, never [object Object]', () => {
  it('shows the error string of a 403 body', () => {
    const msg = describePickError(axiosErr(403, { error: 'Only tournament staff or the captain for this round can make picks' })).message;
    expect(msg).toBe('Failed to update captains: Only tournament staff or the captain for this round can make picks');
  });
  it('shows a DRF detail string', () => {
    expect(describePickError(axiosErr(401, { detail: 'Not signed in' })).message).toBe('Failed to update captains: Not signed in');
  });
  it('names the stale pick when not_active_round has no active pick', () => {
    const info = describePickError(axiosErr(409, { code: 'not_active_round', active_pick_number: null }));
    expect(info).toEqual({ message: 'That pick is no longer active', jumpToPickNumber: null });
  });
  it.each([
    [400, { user_pk: ['This field is required.'] }],
    [500, {}],
  ])('never renders [object Object] for a %s body without a message', (status, body) => {
    expect(describePickError(axiosErr(status, body)).message).not.toContain('[object Object]');
  });
  it('uses the request error message when there is no response', () => {
    expect(describePickError(new Error('Network Error')).message).toBe('Failed to update captains: Network Error');
  });
});
