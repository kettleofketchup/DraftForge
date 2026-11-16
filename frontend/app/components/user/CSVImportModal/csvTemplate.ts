import type { CSVImportRow } from '~/components/api/api';
import type { UserType } from '~/components/user/types';

import type { CSVRow } from './types';

export function buildExampleCSV(isTournament: boolean): string {
  const comment =
    '# A steam_friend_id, discord_id, or discord_username is required. mmr, positions, team_name, team_captain are optional.';
  const headers = [
    'steam_friend_id',
    'discord_id',
    'discord_username',
    'mmr',
    'positions',
  ];
  if (isTournament) headers.push('team_name', 'team_captain');

  const rows = isTournament
    ? [
        ['76561198012345678', '', 'player1', '5000', '1:3:2', 'Team A', 'true'],
        ['', '123456789012345678', '', '4500', '4:5', 'Team B', ''],
      ]
    : [
        ['76561198012345678', '', 'player1', '5000', '1:3:2'],
        ['', '123456789012345678', '', '4500', '4:5'],
      ];

  return [comment, headers.join(','), ...rows.map((r) => r.join(','))].join(
    '\n',
  );
}

export function toImportRow(raw: CSVRow): CSVImportRow {
  return {
    steam_friend_id: raw.steam_friend_id?.trim() || undefined,
    discord_id: raw.discord_id?.trim() || undefined,
    discord_username: raw.discord_username?.trim() || undefined,
    mmr: raw.mmr?.trim() ? Number(raw.mmr.trim()) : null,
    team_name: raw.team_name?.trim() || undefined,
    team_captain: Boolean(raw.team_captain?.trim()),
    positions: raw.positions?.trim() || undefined,
  };
}

export function buildResolveRow(
  selectedUser: Pick<UserType, 'steam_account_id' | 'discordId'>,
  originalRaw: CSVRow | undefined,
): CSVImportRow {
  const row: CSVImportRow = {};
  if (selectedUser.steam_account_id) {
    row.steam_friend_id = String(selectedUser.steam_account_id);
  } else if (selectedUser.discordId) {
    row.discord_id = selectedUser.discordId;
  }
  if (originalRaw?.mmr?.trim()) {
    row.mmr = Number(originalRaw.mmr.trim());
  }
  if (originalRaw?.team_name?.trim()) {
    row.team_name = originalRaw.team_name.trim();
  }
  if (originalRaw?.team_captain?.trim()) {
    row.team_captain = true;
  }
  if (originalRaw?.positions?.trim()) {
    row.positions = originalRaw.positions.trim();
  }
  return row;
}
