import { describe, expect, it } from 'vitest';

import { parseCSV, validateRows } from '../csvParser';
import { buildExampleCSV, buildResolveRow, toImportRow } from '../csvTemplate';

function headerLine(csv: string): string {
  return csv.split('\n').filter((line) => !line.startsWith('#'))[0];
}

describe('CSV import template', () => {
  it('org template header has no name column', () => {
    expect(headerLine(buildExampleCSV(false))).toBe(
      'steam_friend_id,discord_id,discord_username,mmr,positions',
    );
  });

  it('tournament template header has no name column', () => {
    expect(headerLine(buildExampleCSV(true))).toBe(
      'steam_friend_id,discord_id,discord_username,mmr,positions,team_name,team_captain',
    );
  });

  it('template rows match the header width and the comment omits name', () => {
    for (const isTournament of [false, true]) {
      const csv = buildExampleCSV(isTournament);
      const lines = csv.split('\n');
      expect(lines[0]).not.toMatch(/\bname\b/);
      const width = headerLine(csv).split(',').length;
      for (const row of lines.slice(2)) {
        expect(row.split(',')).toHaveLength(width);
      }
    }
  });
});

describe('CSV with a name column', () => {
  it('still parses and validates without errors', async () => {
    const file = new File(
      ['steam_friend_id,name,mmr\n76561198900000001,Shadow,7200\n'],
      'legacy.csv',
      { type: 'text/csv' },
    );
    const result = await parseCSV(file);
    expect(result.errors).toEqual([]);
    expect(result.data).toHaveLength(1);
    expect(validateRows(result.data)[0].status).toBe('valid');
  });

  it('rows sent to the import API carry no name', () => {
    const row = toImportRow({
      steam_friend_id: '76561198900000001',
      name: 'Shadow',
      mmr: '7200',
      team_name: 'Dire Wolves',
      team_captain: 'true',
      positions: '1:3:2',
    });
    expect(row).not.toHaveProperty('name');
    expect(row).toMatchObject({
      steam_friend_id: '76561198900000001',
      mmr: 7200,
      team_name: 'Dire Wolves',
      team_captain: true,
      positions: '1:3:2',
    });
  });

  it('conflict-resolution rows carry no name', () => {
    const row = buildResolveRow({ steam_account_id: 40000001 } as never, {
      name: 'Shadow',
      mmr: '7200',
    });
    expect(row).not.toHaveProperty('name');
    expect(row).toEqual({ steam_friend_id: '40000001', mmr: 7200 });
  });
});
