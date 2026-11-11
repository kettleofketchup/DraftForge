import { describe, expect, it } from 'vitest';
import {
  PLAYER_STATUS_LABELS,
  isInLobby,
  needsInvite,
  playerStatusLabel,
  playerStatusText,
} from '../players';
import { LobbyPlayerSchema, type LobbyPlayer } from '../schemas';
import { players } from './fixtures';

const base = LobbyPlayerSchema.parse(players[1]);

function player(overrides: Partial<LobbyPlayer>): LobbyPlayer {
  return { ...base, invites_sent: 1, ...overrides };
}

// Every status dota_lobby reports for a player, and '' before it reports one.
const STATUSES = ['', 'pending', 'invited', 'joined', 'seated', 'left', 'kicked'];

describe('playerStatusLabel', () => {
  it.each(STATUSES)('gives %j a capitalised label', (status) => {
    const label = playerStatusLabel(status);
    expect(label).toBe(PLAYER_STATUS_LABELS[status]);
    expect(label).not.toBe(status);
    expect(label.charAt(0)).toBe(label.charAt(0).toUpperCase());
    expect(label.charAt(0)).toMatch(/[A-Z]/);
  });

  it('labels every known status', () => {
    expect(Object.keys(PLAYER_STATUS_LABELS).sort()).toEqual([...STATUSES].sort());
  });

  it('never shows the raw pending status', () => {
    expect(playerStatusText(player({ status: 'pending' }))).toBe('Invite pending');
  });

  it('capitalises a status it does not know', () => {
    expect(playerStatusLabel('on_hold')).toBe('On hold');
    expect(playerStatusLabel(null)).toBe('Not invited');
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
    expect(playerStatusText(player(overrides))).toBe(text);
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
