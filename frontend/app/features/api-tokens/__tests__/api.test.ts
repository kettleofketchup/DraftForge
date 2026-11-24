import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ZodError } from 'zod';

const { get, post, put, del } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  del: vi.fn(),
}));

vi.mock('~/components/api/axios', () => ({
  default: { get, post, put, delete: del },
}));

import {
  createApiToken,
  getApiLimits,
  getApiUsage,
  listApiTokens,
  putApiLimits,
  revokeApiToken,
} from '../api';
import { ApiLimitsFormSchema, CreateTokenFormSchema } from '../schemas';
import { apiToken, apiUsage, createdApiToken } from './fixtures';

beforeEach(() => {
  get.mockReset();
  post.mockReset();
  put.mockReset();
  del.mockReset();
});

describe('api-tokens api', () => {
  it('lists tokens', async () => {
    const rows = [
      apiToken(),
      apiToken({
        id: 2,
        user: null,
        revoked_at: '2026-11-02T00:00:00Z',
        revoked_by: { pk: 1, username: null },
      }),
    ];
    get.mockResolvedValue({ data: rows });
    await expect(listApiTokens(7)).resolves.toEqual(rows);
    expect(get).toHaveBeenCalledWith('/organizations/7/api-tokens/');
  });

  it('rejects a malformed token list', async () => {
    get.mockResolvedValue({ data: [{ id: 'x' }] });
    await expect(listApiTokens(7)).rejects.toBeInstanceOf(ZodError);
  });

  it('creates a token and keeps the raw secret', async () => {
    post.mockResolvedValue({ data: createdApiToken() });
    const created = await createApiToken(7, 'MMR bot');
    expect(created.token).toBe('dfk_abcd1234_secretsecret');
    expect(post).toHaveBeenCalledWith('/organizations/7/api-tokens/', {
      name: 'MMR bot',
    });
  });

  it('rejects a create response without the secret', async () => {
    post.mockResolvedValue({ data: apiToken() });
    await expect(createApiToken(7, 'x')).rejects.toBeInstanceOf(ZodError);
  });

  it('revokes a token', async () => {
    const revoked = apiToken({ revoked_at: '2026-11-03T00:00:00Z' });
    del.mockResolvedValue({ data: revoked });
    await expect(revokeApiToken(7, 1)).resolves.toEqual(revoked);
    expect(del).toHaveBeenCalledWith('/organizations/7/api-tokens/1/');
  });

  it('gets usage with the day window', async () => {
    get.mockResolvedValue({ data: apiUsage() });
    const usage = await getApiUsage(7, 30);
    expect(usage.users[0].requests).toBe(42);
    expect(get).toHaveBeenCalledWith('/organizations/7/api-tokens/usage/', {
      params: { days: 30 },
    });
  });

  it('gets and puts limits', async () => {
    get.mockResolvedValue({ data: { per_minute: 60, per_day: 5000 } });
    await expect(getApiLimits(7)).resolves.toEqual({
      per_minute: 60,
      per_day: 5000,
    });
    expect(get).toHaveBeenCalledWith('/organizations/7/api-limits/');

    put.mockResolvedValue({ data: { per_minute: 10, per_day: 100 } });
    await putApiLimits(7, { per_minute: 10, per_day: 100 });
    expect(put).toHaveBeenCalledWith('/organizations/7/api-limits/', {
      per_minute: 10,
      per_day: 100,
    });
  });
});

describe('form schemas', () => {
  it('trims and bounds the token name', () => {
    expect(CreateTokenFormSchema.parse({ name: '  bot  ' })).toEqual({
      name: 'bot',
    });
    expect(CreateTokenFormSchema.safeParse({ name: '   ' }).success).toBe(
      false,
    );
    expect(
      CreateTokenFormSchema.safeParse({ name: 'x'.repeat(65) }).success,
    ).toBe(false);
  });

  it('matches the backend limit ranges', () => {
    const ok = (per_minute: number, per_day: number) =>
      ApiLimitsFormSchema.safeParse({ per_minute, per_day }).success;
    expect(ok(1, 1)).toBe(true);
    expect(ok(10_000, 1_000_000)).toBe(true);
    expect(ok(0, 1)).toBe(false);
    expect(ok(10_001, 1)).toBe(false);
    expect(ok(1, 1_000_001)).toBe(false);
    expect(ok(1.5, 1)).toBe(false);
    expect(ok(Number.NaN, 1)).toBe(false);
  });
});
