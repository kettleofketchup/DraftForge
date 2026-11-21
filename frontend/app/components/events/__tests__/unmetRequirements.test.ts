import { describe, expect, it } from 'vitest';
import {
  UNMET_CODES,
  UNMET_REQUIREMENT_LABELS,
  describeUnmet,
  signupHoldReason,
  signupSuccessMessage,
} from '../unmetRequirements';

describe('unmet requirement labels', () => {
  it('labels cover every backend code', () => {
    for (const c of UNMET_CODES)
      expect(UNMET_REQUIREMENT_LABELS[c]).toBeTruthy();
  });

  it('describeUnmet joins labels in order', () => {
    expect(describeUnmet(['dota_rank_undeclared', 'below_min_mmr'])).toBe(
      'Rank not declared, Below minimum MMR',
    );
  });

  it('labels the conduct threshold code', () => {
    expect(describeUnmet(['conduct_below_threshold'])).toBe(
      'Attendance record below org threshold',
    );
  });

  it('describeUnmet tolerates a missing field and unknown codes', () => {
    expect(describeUnmet(undefined)).toBe('');
    expect(describeUnmet([])).toBe('');
    expect(describeUnmet(['some_future_code'])).toBe('some_future_code');
  });
});

describe('signupHoldReason', () => {
  const codes = ['rank_screenshot_missing'];

  it('describes a pending-approval row', () => {
    expect(
      signupHoldReason(
        { status: 'pending_approval', unmet_requirements: codes },
        true,
      ),
    ).toBe('Rank screenshot missing');
  });

  it('describes RSVP rows only on manual-approval events', () => {
    const row = { status: 'rsvp', unmet_requirements: codes };
    expect(signupHoldReason(row, false)).toBe('Rank screenshot missing');
    expect(signupHoldReason(row, true)).toBeNull();
  });

  it('returns null without codes or for other statuses', () => {
    expect(
      signupHoldReason(
        { status: 'pending_approval', unmet_requirements: [] },
        true,
      ),
    ).toBeNull();
    expect(signupHoldReason({ status: 'pending_approval' }, true)).toBeNull();
    expect(
      signupHoldReason(
        { status: 'approved', unmet_requirements: codes },
        false,
      ),
    ).toBeNull();
  });
});

describe('signupSuccessMessage', () => {
  it('says pending approval when the signup is held', () => {
    expect(signupSuccessMessage('rsvp', 'pending_approval')).toBe(
      'Signed up, pending approval',
    );
    expect(signupSuccessMessage('tentative', 'pending_approval')).toBe(
      'Signed up, pending approval',
    );
  });

  it('keeps the intent messages otherwise', () => {
    expect(signupSuccessMessage('rsvp', 'rsvp')).toBe('Signed up!');
    expect(signupSuccessMessage('tentative', 'tentative')).toBe(
      'Marked as tentative!',
    );
    expect(signupSuccessMessage('rsvp', undefined)).toBe('Signed up!');
  });
});
