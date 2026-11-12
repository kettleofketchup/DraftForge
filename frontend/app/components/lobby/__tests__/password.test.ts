import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import {
  LOBBY_PASSWORD_MAX_LENGTH,
  lobbyPasswordIssue,
  lobbyPasswordPayload,
  refineLobbyPassword,
} from '../password';

describe('lobbyPasswordIssue', () => {
  it('accepts printable ASCII up to the limit', () => {
    for (const value of ['a', 'Team Night #4!', 'x'.repeat(LOBBY_PASSWORD_MAX_LENGTH)]) {
      expect(lobbyPasswordIssue(value)).toBeNull();
    }
  });

  it('names what is wrong', () => {
    expect(lobbyPasswordIssue('')).toBe('required');
    expect(lobbyPasswordIssue(undefined)).toBe('required');
    expect(lobbyPasswordIssue('x'.repeat(LOBBY_PASSWORD_MAX_LENGTH + 1))).toBe('too_long');
    expect(lobbyPasswordIssue('pässword')).toBe('invalid_characters');
    expect(lobbyPasswordIssue('tab\there')).toBe('invalid_characters');
    expect(lobbyPasswordIssue(' leading')).toBe('surrounding_spaces');
    expect(lobbyPasswordIssue('trailing ')).toBe('surrounding_spaces');
  });
});

describe('refineLobbyPassword', () => {
  const schema = z
    .object({
      dota_lobby_password_mode: z.enum(['random', 'fixed']),
      dota_lobby_password: z.string(),
    })
    .superRefine(refineLobbyPassword);

  it('only checks fixed passwords', () => {
    expect(
      schema.safeParse({ dota_lobby_password_mode: 'random', dota_lobby_password: '' }).success,
    ).toBe(true);
    expect(
      schema.safeParse({ dota_lobby_password_mode: 'fixed', dota_lobby_password: 'ok' }).success,
    ).toBe(true);
  });

  it('reports the issue code on the password field', () => {
    const result = schema.safeParse({ dota_lobby_password_mode: 'fixed', dota_lobby_password: ' x' });
    expect(result.success).toBe(false);
    expect(result.error?.issues[0].path).toEqual(['dota_lobby_password']);
    expect(result.error?.issues[0].message).toBe('surrounding_spaces');
  });
});

describe('lobbyPasswordPayload', () => {
  it('never sends a password in random mode', () => {
    expect(
      lobbyPasswordPayload({ dota_lobby_password_mode: 'random', dota_lobby_password: 'stale' }),
    ).toEqual({ dota_lobby_password_mode: 'random' });
    expect(lobbyPasswordPayload({})).toEqual({ dota_lobby_password_mode: 'random' });
  });

  it('sends the fixed password', () => {
    expect(
      lobbyPasswordPayload({ dota_lobby_password_mode: 'fixed', dota_lobby_password: 'pw' }),
    ).toEqual({ dota_lobby_password_mode: 'fixed', dota_lobby_password: 'pw' });
  });
});
