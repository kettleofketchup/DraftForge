// Display text and invite rules for the players of a lobby's roster.
import type { LobbyPlayer } from './schemas';

// dota_lobby's player statuses, plus '' for a player the lobby has not
// reported on yet (no lobby, or the roster changed since).
export const PLAYER_STATUS_LABELS: Record<string, string> = {
  '': 'Not invited',
  pending: 'Invite pending',
  invited: 'Invited',
  joined: 'In lobby',
  seated: 'Seated',
  left: 'Left the lobby',
  kicked: 'Kicked',
};

/** A status this UI does not know yet, as a readable label: `on_hold` -> `On hold`. */
function humanize(value: string): string {
  const text = value.replace(/_/g, ' ').trim();
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : '';
}

export function playerStatusLabel(status: string | null | undefined): string {
  const key = status ?? '';
  return PLAYER_STATUS_LABELS[key] ?? humanize(key);
}

// A seat on a team (`radiant`, `dire_3`), and the named seats off the teams.
const TEAM_SEAT = /^(radiant|dire)(_|$)/;
const OFF_TEAM_SEATS = new Set(['player_pool', 'spectator', 'broadcaster']);

/** `radiant_1` -> `Radiant 1`, `player_pool` -> `Player pool`. */
export function seatLabel(seat: string): string {
  return humanize(seat);
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
export function playerStatusText(player: LobbyPlayer): string {
  if (player.account_id === null) return 'No Steam account';
  if (player.seat) {
    if (TEAM_SEAT.test(player.seat)) {
      const parts = [playerStatusLabel('seated'), seatLabel(player.seat)];
      if (player.ready) parts.push('Ready');
      return parts.join(' · ');
    }
    // In the lobby but not on a team: the pool, a spectator or broadcaster
    // slot, or a slot dota_lobby could not read.
    const inLobby = playerStatusLabel('joined');
    return OFF_TEAM_SEATS.has(player.seat)
      ? `${inLobby} · ${seatLabel(player.seat)}`
      : inLobby;
  }
  if (player.status === 'invited' && player.invites_sent > 1) {
    return `${playerStatusLabel('invited')} (${player.invites_sent}×)`;
  }
  return playerStatusLabel(player.status);
}
