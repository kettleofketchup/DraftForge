import { describe, expect, it } from 'vitest';
import { canSeeEventOpsNotices } from '../opsNoticesAccess';

describe('canSeeEventOpsNotices', () => {
  it('is true for an operator who cannot manage the event', () => {
    expect(
      canSeeEventOpsNotices({
        user_is_event_operator: true,
        user_can_manage: false,
      }),
    ).toBe(true);
  });

  it('follows the operator flag over user_can_manage', () => {
    expect(
      canSeeEventOpsNotices({
        user_is_event_operator: false,
        user_can_manage: true,
      }),
    ).toBe(false);
  });

  it('falls back to user_can_manage when the flag is absent', () => {
    expect(canSeeEventOpsNotices({ user_can_manage: true })).toBe(true);
  });

  it('is false for a missing event', () => {
    expect(canSeeEventOpsNotices(null)).toBe(false);
    expect(canSeeEventOpsNotices(undefined)).toBe(false);
  });
});
