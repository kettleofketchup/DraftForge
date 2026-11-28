import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ZodError } from 'zod';

const { get, patch } = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn() }));

vi.mock('~/components/api/axios', () => ({ default: { get, patch } }));

import {
  getOrgSettings,
  patchOrgSettings,
  signupRetentionFormSchema,
  toRetentionPatch,
} from '../orgSettingsAPI';

const SETTINGS = {
  organization: 7,
  staff_override_policy: 'silent',
  staff_override_warning_codes: ['over_capacity'],
  available_warning_codes: [{ code: 'over_capacity', label: 'Over capacity' }],
  signup_record_retention_days: null,
  signup_record_min_retention_days: 30,
  updated_at: '2026-11-27T12:00:00Z',
};

beforeEach(() => {
  get.mockReset();
  patch.mockReset();
});

describe('org settings retention fields', () => {
  it('parses null retention and the server minimum', async () => {
    get.mockResolvedValue({ data: SETTINGS });
    const parsed = await getOrgSettings(7);
    expect(get).toHaveBeenCalledWith('/organizations/7/settings/');
    expect(parsed.signup_record_retention_days).toBeNull();
    expect(parsed.signup_record_min_retention_days).toBe(30);
  });

  it('parses a retention period', async () => {
    get.mockResolvedValue({
      data: { ...SETTINGS, signup_record_retention_days: 400 },
    });
    expect((await getOrgSettings(7)).signup_record_retention_days).toBe(400);
  });

  it('rejects a body without the minimum', async () => {
    const { signup_record_min_retention_days: _, ...rest } = SETTINGS;
    get.mockResolvedValue({ data: rest });
    await expect(getOrgSettings(7)).rejects.toBeInstanceOf(ZodError);
  });

  it('patches retention days', async () => {
    patch.mockResolvedValue({
      data: { ...SETTINGS, signup_record_retention_days: 365 },
    });
    const parsed = await patchOrgSettings(7, {
      signup_record_retention_days: 365,
    });
    expect(patch).toHaveBeenCalledWith('/organizations/7/settings/', {
      signup_record_retention_days: 365,
    });
    expect(parsed.signup_record_retention_days).toBe(365);
  });
});

describe('signupRetentionFormSchema', () => {
  const schema = signupRetentionFormSchema(30);

  it('accepts forever with null days', () => {
    expect(
      schema.safeParse({
        retention_mode: 'forever',
        signup_record_retention_days: null,
      }).success,
    ).toBe(true);
  });

  it('rejects a period below the minimum', () => {
    const result = schema.safeParse({
      retention_mode: 'period',
      signup_record_retention_days: 29,
    });
    expect(result.success).toBe(false);
    expect(result.error?.issues[0]?.message).toBe('Minimum 30 days.');
    expect(result.error?.issues[0]?.path).toEqual([
      'signup_record_retention_days',
    ]);
  });

  it('accepts a period at or above the minimum', () => {
    expect(
      schema.safeParse({
        retention_mode: 'period',
        signup_record_retention_days: 365,
      }).success,
    ).toBe(true);
    expect(
      schema.safeParse({
        retention_mode: 'period',
        signup_record_retention_days: 30,
      }).success,
    ).toBe(true);
  });

  it('requires days for a period', () => {
    const result = schema.safeParse({
      retention_mode: 'period',
      signup_record_retention_days: null,
    });
    expect(result.success).toBe(false);
    expect(result.error?.issues[0]?.path).toEqual([
      'signup_record_retention_days',
    ]);
  });

  it('rejects a period above the maximum', () => {
    expect(
      schema.safeParse({
        retention_mode: 'period',
        signup_record_retention_days: 36501,
      }).success,
    ).toBe(false);
  });

  it('uses the given minimum', () => {
    expect(
      signupRetentionFormSchema(60).safeParse({
        retention_mode: 'period',
        signup_record_retention_days: 45,
      }).error?.issues[0]?.message,
    ).toBe('Minimum 60 days.');
  });
});

describe('toRetentionPatch', () => {
  it('maps forever to null', () => {
    expect(
      toRetentionPatch({
        retention_mode: 'forever',
        signup_record_retention_days: 365,
      }),
    ).toEqual({ signup_record_retention_days: null });
  });

  it('maps a period to its days', () => {
    expect(
      toRetentionPatch({
        retention_mode: 'period',
        signup_record_retention_days: 400,
      }),
    ).toEqual({ signup_record_retention_days: 400 });
  });
});
