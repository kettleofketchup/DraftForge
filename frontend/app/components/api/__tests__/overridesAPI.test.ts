import { AxiosError, AxiosHeaders } from 'axios';
import { describe, expect, it } from 'vitest';

import {
  getOverrideRequired,
  isOverrideReasonRequiredError,
  isOverrideRequiredError,
  isStaffReasonRequiredError,
  OverrideReasonFormSchema,
  overrideReasonFormSchema,
  responseBody,
  staffReasonFormSchema,
} from '../overridesAPI';

function axiosError(status: number, data: unknown): AxiosError {
  return new AxiosError('fail', 'ERR_BAD_REQUEST', undefined, undefined, {
    status,
    statusText: '',
    data,
    headers: {},
    config: { headers: new AxiosHeaders() },
  });
}

const body = {
  code: 'override_required',
  blocked: false,
  violations: [
    {
      code: 'below_min_mmr',
      rule: 'staff-override',
      category: 'eligibility',
      message: "MMR 2,400 is below Roster A's 3,000 gate",
      blocking: false,
      params: { mmr: 2400, min_mmr: 3000 },
    },
  ],
};

describe('override error guards', () => {
  it('parses a 409 override body', () => {
    const parsed = getOverrideRequired(axiosError(409, body));
    expect(parsed?.violations[0].params).toEqual({ mmr: 2400, min_mmr: 3000 });
    expect(isOverrideRequiredError(axiosError(409, body))).toBe(true);
  });

  it('rejects other statuses, codes and malformed bodies', () => {
    expect(getOverrideRequired(axiosError(400, body))).toBeNull();
    expect(
      getOverrideRequired(axiosError(409, { code: 'conflict' })),
    ).toBeNull();
    expect(
      getOverrideRequired(
        axiosError(409, { ...body, violations: [{ code: 'x' }] }),
      ),
    ).toBeNull();
    expect(isOverrideRequiredError(new Error('boom'))).toBe(false);
    expect(isOverrideRequiredError(undefined)).toBe(false);
  });

  it('detects the 400 reason error', () => {
    expect(
      isOverrideReasonRequiredError(
        axiosError(400, { code: 'override_reason_required' }),
      ),
    ).toBe(true);
    expect(
      isOverrideReasonRequiredError(axiosError(400, { reason: ['x'] })),
    ).toBe(false);
    expect(
      isOverrideReasonRequiredError(
        axiosError(409, { code: 'override_reason_required' }),
      ),
    ).toBe(false);
  });
});

describe('OverrideReasonFormSchema', () => {
  it('trims and bounds the reason', () => {
    expect(OverrideReasonFormSchema.safeParse({ reason: '   ' }).success).toBe(
      false,
    );
    expect(
      OverrideReasonFormSchema.safeParse({ reason: 'x'.repeat(501) }).success,
    ).toBe(false);
    expect(
      OverrideReasonFormSchema.parse({ reason: `  ${'x'.repeat(500)} ` }),
    ).toEqual({
      reason: 'x'.repeat(500),
    });
  });
});

describe('overrideReasonFormSchema', () => {
  it('uses the length message above a minimum of one', () => {
    const result = overrideReasonFormSchema(3).safeParse({ reason: ' ab ' });
    expect(result.success).toBe(false);
    expect(result.error?.issues[0].message).toBe(
      'Give a reason (at least 3 characters).',
    );
    expect(overrideReasonFormSchema(3).parse({ reason: ' abc ' })).toEqual({
      reason: 'abc',
    });
  });

  it('keeps the required message at a minimum of one', () => {
    const result = overrideReasonFormSchema(1).safeParse({ reason: ' ' });
    expect(result.error?.issues[0].message).toBe('A reason is required');
  });
});

describe('staff reason guard', () => {
  it('detects the 400 reason_required body', () => {
    expect(
      isStaffReasonRequiredError(axiosError(400, { error: 'reason_required' })),
    ).toBe(true);
  });

  it('ignores other bodies, statuses and errors', () => {
    expect(
      isStaffReasonRequiredError(axiosError(400, { error: 'other' })),
    ).toBe(false);
    expect(
      isStaffReasonRequiredError(
        axiosError(409, { code: 'override_reason_required' }),
      ),
    ).toBe(false);
    expect(
      isStaffReasonRequiredError(axiosError(409, { error: 'reason_required' })),
    ).toBe(false);
    expect(isStaffReasonRequiredError(new Error('boom'))).toBe(false);
  });

  it('exposes the body for a matching status only', () => {
    expect(responseBody(axiosError(400, { a: 1 }), 400)).toEqual({ a: 1 });
    expect(responseBody(axiosError(400, { a: 1 }), 409)).toBeUndefined();
  });
});

describe('staffReasonFormSchema', () => {
  it('accepts an empty reason when optional', () => {
    expect(staffReasonFormSchema(false).safeParse({ reason: '' }).success).toBe(
      true,
    );
  });

  it('rejects whitespace when required', () => {
    const result = staffReasonFormSchema(true).safeParse({ reason: '   ' });
    expect(result.success).toBe(false);
    expect(result.error?.issues[0].message).toBe('A reason is required');
  });

  it.each([false, true])('bounds the reason at 500 (required=%s)', (req) => {
    expect(
      staffReasonFormSchema(req).safeParse({ reason: 'x'.repeat(501) }).success,
    ).toBe(false);
    expect(
      staffReasonFormSchema(req).parse({ reason: ` ${'x'.repeat(500)} ` }),
    ).toEqual({ reason: 'x'.repeat(500) });
  });
});
