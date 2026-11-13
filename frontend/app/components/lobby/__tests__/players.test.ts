import { describe, expect, it } from 'vitest';
import { createI18nInstance } from '~/i18n/config';
import en from '~/i18n/locales/en/lobby.json';
import {
  PLAYER_STATUSES,
  isInLobby,
  needsInvite,
  playerStatusLabel,
  playerStatusText,
  seatLabel,
} from '../players';
import { LobbyPlayerSchema, type LobbyPlayer } from '../schemas';
import { players } from './fixtures';

const base = LobbyPlayerSchema.parse(players[1]);
const t = createI18nInstance('en').getFixedT('en', 'lobby');
const tEs = createI18nInstance('es').getFixedT('es', 'lobby');

function player(overrides: Partial<LobbyPlayer>): LobbyPlayer {
  return { ...base, invites_sent: 1, ...overrides };
}

describe('playerStatusLabel', () => {
  it.each(PLAYER_STATUSES)('gives %j a capitalised, translated label', (status) => {
    const label = playerStatusLabel(status, t);
    expect(Object.values(en.player.status)).toContain(label);
    expect(label).not.toBe(status);
    expect(label.charAt(0)).toMatch(/[A-Z]/);
  });

  it('never shows the raw pending status', () => {
    expect(playerStatusText(player({ status: 'pending' }), t)).toBe('Invite pending');
  });

  it('capitalises a status it does not know', () => {
    expect(playerStatusLabel('on_hold', t)).toBe('On hold');
    expect(playerStatusLabel(null, t)).toBe('Not invited');
  });
});

describe('seatLabel', () => {
  it.each([
    ['radiant_1', 'Radiant 1'],
    ['dire', 'Dire'],
    ['player_pool', 'Player pool'],
    ['spectator', 'Spectator'],
    ['coach_slot', 'Coach slot'],
  ])('%j reads %j', (seat, text) => {
    expect(seatLabel(seat, t)).toBe(text);
  });
});

describe('playerStatusText', () => {
  it.each([
    [{ account_id: null, status: '' }, 'No Steam account'],
    [{ status: 'invited', invites_sent: 1 }, 'Invited'],
    [{ status: 'invited', invites_sent: 3 }, 'Invited (3×)'],
    [{ status: 'joined', seat: 'radiant_1', ready: true }, 'Seated · Radiant 1 · Ready'],
    [{ status: 'seated', seat: 'dire', ready: false }, 'Seated · Dire'],
    [{ status: 'joined', seat: 'player_pool' }, 'In lobby · Player pool'],
    [{ status: 'joined', seat: 'unknown' }, 'In lobby'],
    [{ status: 'joined', seat: null }, 'In lobby'],
    [{ status: 'left' }, 'Left the lobby'],
    [{ status: 'kicked' }, 'Kicked'],
    [{ status: '' }, 'Not invited'],
  ] as [Partial<LobbyPlayer>, string][])('%o reads %j', (overrides, text) => {
    expect(playerStatusText(player(overrides), t)).toBe(text);
  });

  it('follows the selected language', () => {
    expect(playerStatusText(player({ status: 'pending' }), tEs)).toBe('Invitación pendiente');
    expect(
      playerStatusText(player({ status: 'joined', seat: 'radiant_1', ready: true }), tEs),
    ).toBe('Sentado · Radiant 1 · Listo');
    expect(playerStatusText(player({ account_id: null }), tEs)).toBe('Sin cuenta de Steam');
  });
});

describe('needsInvite', () => {
  it('is true only for linked players outside the lobby', () => {
    expect(needsInvite(player({ status: 'invited' }))).toBe(true);
    expect(needsInvite(player({ status: 'pending' }))).toBe(true);
    expect(needsInvite(player({ status: 'left' }))).toBe(true);
    expect(needsInvite(player({ status: 'joined', seat: 'radiant_1' }))).toBe(false);
    expect(needsInvite(player({ status: 'joined' }))).toBe(false);
    expect(needsInvite(player({ account_id: null, status: '' }))).toBe(false);
    expect(isInLobby(player({ status: 'seated' }))).toBe(true);
  });
});
