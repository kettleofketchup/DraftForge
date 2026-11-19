import { describe, expect, it } from 'vitest';
import { canRecordAttendance } from '../canRecordAttendance';

describe('canRecordAttendance', () => {
  it('allows league staff who can manage the event without org staff', () => {
    expect(
      canRecordAttendance({ user_can_manage: true }, { features: ['conduct'] }),
    ).toBe(true);
  });

  it('refuses an org member who cannot manage the event', () => {
    expect(
      canRecordAttendance(
        { user_can_manage: false },
        { features: ['conduct'] },
      ),
    ).toBe(false);
  });

  it('refuses when conduct is not an active feature', () => {
    expect(
      canRecordAttendance(
        { user_can_manage: true },
        { features: ['contributions'] },
      ),
    ).toBe(false);
  });

  it('refuses while the event or org is not loaded', () => {
    expect(canRecordAttendance(undefined, { features: ['conduct'] })).toBe(
      false,
    );
    expect(canRecordAttendance({ user_can_manage: true }, undefined)).toBe(
      false,
    );
  });
});
