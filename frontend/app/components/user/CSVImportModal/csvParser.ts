import Papa from 'papaparse';
import type { CSVRow, ValidatedRow } from './types';

const VALID_HEADERS = ['steam_friend_id', 'discord_id', 'base_mmr', 'team_name'];

export function parseCSV(file: File): Promise<Papa.ParseResult<CSVRow>> {
  return new Promise((resolve, reject) => {
    Papa.parse<CSVRow>(file, {
      header: true,
      skipEmptyLines: true,
      transformHeader: (header) => header.trim().toLowerCase(),
      complete: resolve,
      error: reject,
    });
  });
}

export function validateRows(rows: CSVRow[]): ValidatedRow[] {
  return rows.map((row, index) => {
    const steamId = row.steam_friend_id?.trim();
    const discordId = row.discord_id?.trim();
    const baseMmr = row.base_mmr?.trim();

    // Must have at least one identifier
    if (!steamId && !discordId) {
      return {
        index,
        raw: row,
        status: 'error' as const,
        message: 'Missing identifier (need steam_friend_id or discord_id)',
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

    // Validate base_mmr is numeric if provided
    if (baseMmr && !/^\d+$/.test(baseMmr)) {
      return {
        index,
        raw: row,
        status: 'error' as const,
        message: `Invalid base_mmr: ${baseMmr}`,
      };
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
