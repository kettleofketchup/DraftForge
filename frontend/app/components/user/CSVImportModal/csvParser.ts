import { parse } from 'csv-parse/browser/esm/sync';
import type { CSVRow, ValidatedRow } from './types';

const VALID_HEADERS = ['steam_friend_id', 'discord_id', 'discord_username', 'name', 'mmr', 'team_name', 'team_captain', 'positions'];

interface ParseCSVResult {
  data: CSVRow[];
  errors: { message: string }[];
}

export async function parseCSV(file: File): Promise<ParseCSVResult> {
  const text = await file.text();
  try {
    const records = parse(text, {
      columns: (header: string[]) => header.map((h) => h.trim().toLowerCase()),
      skip_empty_lines: true,
      relax_column_count: true,
      comment: '#',
    }) as CSVRow[];
    return { data: records, errors: [] };
  } catch (err) {
    return {
      data: [],
      errors: [{ message: err instanceof Error ? err.message : String(err) }],
    };
  }
}

export function validateRows(rows: CSVRow[]): ValidatedRow[] {
  return rows.map((row, index) => {
    const steamId = row.steam_friend_id?.trim();
    const discordId = row.discord_id?.trim();
    const discordUsername = row.discord_username?.trim();
    const mmr = row.mmr?.trim();

    // Must have at least one identifier
    if (!steamId && !discordId && !discordUsername) {
      return {
        index,
        raw: row,
        status: 'error' as const,
        message: 'Missing identifier (need steam_friend_id, discord_id, or discord_username)',
      };
    }

    // Validate steam_friend_id is numeric if provided
    if (steamId && !/^\d+$/.test(steamId)) {
      return {
        index,
        raw: row,
        status: 'error' as const,
        message: `Invalid steam_friend_id: ${steamId}`,
      };
    }

    // Validate discord_id is numeric if provided
    if (discordId && !/^\d+$/.test(discordId)) {
      return {
        index,
        raw: row,
        status: 'error' as const,
        message: `Invalid discord_id: ${discordId}`,
      };
    }

    // Validate mmr is numeric if provided
    if (mmr && !/^\d+$/.test(mmr)) {
      return {
        index,
        raw: row,
        status: 'error' as const,
        message: `Invalid mmr: ${mmr}`,
      };
    }

    // Validate positions format if provided (ranked position numbers 1-5, e.g. "1:3:2")
    const positions = row.positions?.trim();
    if (positions) {
      const parts = positions.split(':');
      const nums = parts.map(Number);
      if (
        parts.length > 5 ||
        parts.some((p) => !/^[1-5]$/.test(p)) ||
        new Set(nums).size !== nums.length
      ) {
        return {
          index,
          raw: row,
          status: 'error' as const,
          message: `Invalid positions: ${positions} (expected ranked position numbers 1-5, e.g. "1:3:2")`,
        };
      }
    }

    return {
      index,
      raw: row,
      status: 'valid' as const,
    };
  });
}

export function getValidHeaders(headers: string[]): {
  valid: string[];
  unknown: string[];
} {
  const normalized = headers.map((h) => h.trim().toLowerCase());
  return {
    valid: normalized.filter((h) => VALID_HEADERS.includes(h)),
    unknown: normalized.filter((h) => !VALID_HEADERS.includes(h) && h !== ''),
  };
}
