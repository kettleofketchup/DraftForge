// Display text and invite rules for the players of a lobby's roster. The text
// comes from the `lobby` i18n namespace; callers pass its `t`.
import type { TFunction } from 'i18next';
import type { LobbyPlayer } from './schemas';

// dota_lobby's player statuses, plus '' for a player the lobby has not
// reported on yet (no lobby, or the roster changed since). Keys are spelled
// out so i18next-parser can extract them.
export const PLAYER_STATUSES = ['', 'pending', 'invited', 'joined', 'seated', 'left', 'kicked'];

function knownStatusLabel(status: string, t: TFunction<'lobby'>): string | undefined {
  switch (status) {
    case '':
      return t('player.status.not_invited');
    case 'pending':
      return t('player.status.pending');
    case 'invited':
      return t('player.status.invited');
    case 'joined':
      return t('player.status.joined');
    case 'seated':
      return t('player.status.seated');
    case 'left':
      return t('player.status.left');
    case 'kicked':
      return t('player.status.kicked');
    default:
      return undefined;
  }
}

/** A value this UI has no text for, as a readable label: `on_hold` -> `On hold`. */
function humanize(value: string): string {
  const text = value.replace(/_/g, ' ').trim();
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : '';
}

export function playerStatusLabel(status: string | null | undefined, t: TFunction<'lobby'>): string {
  const key = status ?? '';
  return knownStatusLabel(key, t) ?? humanize(key);
}

// A seat on a team (`radiant`, `dire_3`), and the named seats off the teams.
const TEAM_SEAT = /^(radiant|dire)(_|$)/;
const NUMBERED_TEAM_SEAT = /^(radiant|dire)(?:_(\d+))?$/;
const OFF_TEAM_SEATS = new Set(['player_pool', 'spectator', 'broadcaster']);

/** `radiant_1` -> `Radiant 1`, `player_pool` -> `Player pool`. */
export function seatLabel(seat: string, t: TFunction<'lobby'>): string {
  const team = NUMBERED_TEAM_SEAT.exec(seat);
  if (team) {
    const [, side, slot] = team;
    if (side === 'radiant') {
      return slot ? t('player.seat.radiant_slot', { slot }) : t('player.seat.radiant');
    }
    return slot ? t('player.seat.dire_slot', { slot }) : t('player.seat.dire');
  }
  switch (seat) {
    case 'player_pool':
      return t('player.seat.player_pool');
    case 'spectator':
      return t('player.seat.spectator');
    case 'broadcaster':
      return t('player.seat.broadcaster');
    default:
      return humanize(seat);
  }
}

/** The player is a member of the in-game lobby (seated or not). */
export function isInLobby(player: LobbyPlayer): boolean {
  return !!player.seat || player.status === 'joined' || player.status === 'seated';
}

/** The player can be invited and is not in the lobby yet. */
export function needsInvite(player: LobbyPlayer): boolean {
  return player.account_id !== null && !isInLobby(player);
}

/** The roster line under a player's name: `Seated · Radiant 1 · Ready`. */
export function playerStatusText(player: LobbyPlayer, t: TFunction<'lobby'>): string {
  if (player.account_id === null) return t('player.no_steam');
  const join = (parts: string[]) => parts.join(t('player.separator'));
  if (player.seat) {
    if (TEAM_SEAT.test(player.seat)) {
      const parts = [playerStatusLabel('seated', t), seatLabel(player.seat, t)];
      if (player.ready) parts.push(t('player.ready'));
      return join(parts);
    }
    // In the lobby but not on a team: the pool, a spectator or broadcaster
    // slot, or a slot dota_lobby could not read.
    const inLobby = playerStatusLabel('joined', t);
    return OFF_TEAM_SEATS.has(player.seat) ? join([inLobby, seatLabel(player.seat, t)]) : inLobby;
  }
  if (player.status === 'invited' && player.invites_sent > 1) {
    return t('player.status.invited_times', { times: player.invites_sent });
  }
  return playerStatusLabel(player.status, t);
}
