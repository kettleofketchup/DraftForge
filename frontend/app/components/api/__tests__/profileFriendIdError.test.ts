import { AxiosError, AxiosHeaders, type AxiosResponse } from 'axios';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../axios', () => ({ default: {} }));

import { profileFriendIdError } from '../userAPI';

function httpError(status: number, data: unknown): AxiosError {
  const response = {
    status,
    data,
    statusText: '',
    headers: {},
    config: { headers: new AxiosHeaders() },
  } as AxiosResponse;
  return new AxiosError(
    'failed',
    String(status),
    undefined,
    undefined,
    response,
  );
}

describe('profileFriendIdError', () => {
  it.each([
    [
      400,
      'steam_account_not_found',
      'No Steam account has Friend ID 123. Check the number on your Dota 2 profile or Steam friends page.',
    ],
    [400, 'invalid_friend_id', 'Friend ID must be a number.'],
    [
      429,
      'steam_lookup_rate_limited',
      'Too many Friend ID checks. Try again in an hour.',
    ],
  ])('maps a %i %s to its message', (status, code, message) => {
    expect(
      profileFriendIdError(httpError(status, { error: message, code })),
    ).toBe(message);
  });

  it('maps the 409 duplicate body', () => {
    expect(
      profileFriendIdError(
        httpError(409, {
          error: 'This Friend ID is already linked to another account',
        }),
      ),
    ).toBe('This Friend ID is already linked to another account');
  });

  it('ignores other codes', () => {
    expect(
      profileFriendIdError(httpError(400, { error: 'Bad', code: 'other' })),
    ).toBeNull();
  });

  it('ignores errors without a response', () => {
    expect(profileFriendIdError(new Error('offline'))).toBeNull();
    expect(profileFriendIdError(undefined)).toBeNull();
  });
});
