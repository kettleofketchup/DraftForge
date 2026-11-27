import { expect, it } from 'vitest';
import fixture from '../../../../../backend/discordbot/tests/permission_checks_fixture.json';
import { isExpired, PermissionChecksResponseSchema } from '../schemas';
const result = PermissionChecksResponseSchema.parse(fixture).checks[1];
it('expires at the boundary, rejects missing verified expiry and retains derived expiry', () => {
  expect(isExpired(result, new Date('2026-11-26T12:00:59Z'))).toBe(false);
  expect(isExpired(result, new Date('2026-11-26T12:01:00Z'))).toBe(true);
  expect(isExpired({ ...result, expires_at: null }, new Date())).toBe(true);
  expect(
    isExpired(
      { ...result, status: 'unknown', expires_at: null, expired: true },
      new Date(),
    ),
  ).toBe(true);
  expect(
    isExpired(
      { ...result, status: 'unconfigured', expires_at: null },
      new Date(),
    ),
  ).toBe(false);
});
