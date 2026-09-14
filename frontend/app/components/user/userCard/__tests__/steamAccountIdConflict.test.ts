import { describe, it, expect } from 'vitest';

import {
  shouldLookupSteamAccountId,
  describeSteamAccountIdConflict,
  steamAccountIdConflictFromError,
} from '../steamAccountIdConflict';

const holder = { pk: 275, nickname: 'George Potter', username: 'geo.potter' };

describe('shouldLookupSteamAccountId', () => {
  it('looks up a newly entered id', () => {
    expect(shouldLookupSteamAccountId(765353730, 765353)).toBe(true);
  });

  it('skips when the value is unchanged', () => {
    expect(shouldLookupSteamAccountId(765353, 765353)).toBe(false);
  });

  it('skips when the field is cleared', () => {
    expect(shouldLookupSteamAccountId(null, 765353)).toBe(false);
  });

  it('skips a value that is not a finite number', () => {
    expect(shouldLookupSteamAccountId(Number.NaN, 765353)).toBe(false);
  });

  it('looks up when the user had no id before', () => {
    expect(shouldLookupSteamAccountId(765353730, null)).toBe(true);
  });
});

describe('describeSteamAccountIdConflict', () => {
  it('names the holder by nickname and discord username', () => {
    expect(describeSteamAccountIdConflict(holder, 314)).toBe(
      'Already used by George Potter (@geo.potter). Saving will fail until it is freed from that account.',
    );
  });

  it('falls back to the discord username when there is no nickname', () => {
    expect(
      describeSteamAccountIdConflict({ ...holder, nickname: '' }, 314),
    ).toBe(
      'Already used by @geo.potter. Saving will fail until it is freed from that account.',
    );
  });

  it('reports no conflict when the holder is the user being edited', () => {
    expect(describeSteamAccountIdConflict(holder, 275)).toBeNull();
  });

  it('reports no conflict when the id is free', () => {
    expect(describeSteamAccountIdConflict(null, 314)).toBeNull();
  });
});

describe('steamAccountIdConflictFromError', () => {
  it('extracts the message from a 409 conflict body', () => {
    const body = {
      code: 'steam_account_id_taken',
      error: 'Friend ID 765353730 is already assigned to George Potter (@geo.potter).',
      conflict: holder,
    };
    expect(steamAccountIdConflictFromError(body)).toBe(
      'Friend ID 765353730 is already assigned to George Potter (@geo.potter).',
    );
  });

  it('ignores unrelated error bodies', () => {
    expect(steamAccountIdConflictFromError({ error: 'No valid fields to update' })).toBeNull();
  });

  it('ignores a missing body', () => {
    expect(steamAccountIdConflictFromError(undefined)).toBeNull();
  });

  it('reads the global endpoint validation shape', () => {
    const body = { steam_account_id: ['This Friend ID is already assigned to another account.'] };
    expect(steamAccountIdConflictFromError(body)).toBe(
      'This Friend ID is already assigned to another account.',
    );
  });
});
