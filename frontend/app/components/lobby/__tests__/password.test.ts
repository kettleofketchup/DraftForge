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

  it('lets an empty field keep a saved fixed password', () => {
    const saved = z
      .object({
        dota_lobby_password_mode: z.enum(['random', 'fixed']),
        dota_lobby_password: z.string(),
        dota_lobby_password_saved: z.boolean(),
      })
      .superRefine(refineLobbyPassword);
    expect(
      saved.safeParse({
        dota_lobby_password_mode: 'fixed',
        dota_lobby_password: '',
        dota_lobby_password_saved: true,
      }).success,
    ).toBe(true);
    expect(
      saved.safeParse({
        dota_lobby_password_mode: 'fixed',
        dota_lobby_password: '',
        dota_lobby_password_saved: false,
      }).success,
    ).toBe(false);
    // A typed password is still checked.
    expect(
      saved.safeParse({
        dota_lobby_password_mode: 'fixed',
        dota_lobby_password: ' x',
        dota_lobby_password_saved: true,
      }).success,
    ).toBe(false);
  });

  it('skips forms for another game, where the section is hidden', () => {
    const withGame = z
      .object({
        game_type: z.number(),
        dota_lobby_password_mode: z.enum(['random', 'fixed']),
        dota_lobby_password: z.string(),
      })
      .superRefine(refineLobbyPassword);
    const fixedEmpty = { dota_lobby_password_mode: 'fixed', dota_lobby_password: '' } as const;
    expect(withGame.safeParse({ game_type: 2, ...fixedEmpty }).success).toBe(true);
    expect(withGame.safeParse({ game_type: 1, ...fixedEmpty }).success).toBe(false);
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

  it('sends no password to keep the saved fixed one', () => {
    expect(
      lobbyPasswordPayload({
        dota_lobby_password_mode: 'fixed',
        dota_lobby_password: '',
        dota_lobby_password_saved: true,
      }),
    ).toEqual({ dota_lobby_password_mode: 'fixed' });
    expect(
      lobbyPasswordPayload({
        dota_lobby_password_mode: 'fixed',
        dota_lobby_password: 'new-pw',
        dota_lobby_password_saved: true,
      }),
    ).toEqual({ dota_lobby_password_mode: 'fixed', dota_lobby_password: 'new-pw' });
  });

  it('sends no password fields for another game', () => {
    expect(
      lobbyPasswordPayload({
        game_type: 2,
        dota_lobby_password_mode: 'fixed',
        dota_lobby_password: ' x',
      }),
    ).toEqual({});
  });

  it('sends the fixed password', () => {
    expect(
      lobbyPasswordPayload({ dota_lobby_password_mode: 'fixed', dota_lobby_password: 'pw' }),
    ).toEqual({ dota_lobby_password_mode: 'fixed', dota_lobby_password: 'pw' });
  });
});
