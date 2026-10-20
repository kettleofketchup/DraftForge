/** Friend ID collision helpers for the edit-user form.
 *
 * steam_account_id is unique site-wide, so the form warns on blur rather
 * than letting the save fail. The backend returns the same conflict on save
 * as a backstop (409 from the org endpoint, DRF field errors from the global
 * one), which is what steamAccountIdConflictFromError reads.
 */

export interface SteamAccountIdHolder {
  pk: number;
  nickname: string;
  username: string;
}

const SUFFIX = 'Saving will fail until it is freed from that account.';

export function shouldLookupSteamAccountId(
  value: number | null | undefined,
  original: number | null | undefined,
): boolean {
  if (value === null || value === undefined) return false;
  if (!Number.isFinite(value)) return false;
  return value !== original;
}

export function describeSteamAccountIdConflict(
  holder: SteamAccountIdHolder | null | undefined,
  editingUserPk: number | null | undefined,
): string | null {
  if (!holder) return null;
  if (editingUserPk != null && holder.pk === editingUserPk) return null;
  const who = holder.nickname
    ? `${holder.nickname} (@${holder.username})`
    : `@${holder.username}`;
  return `Already used by ${who}. ${SUFFIX}`;
}

export function steamAccountIdConflictFromError(
  body: unknown,
): string | null {
  if (!body || typeof body !== 'object') return null;
  const data = body as Record<string, unknown>;

  if (data.code === 'steam_account_id_taken' && typeof data.error === 'string') {
    return data.error;
  }

  // Global endpoint: DRF renders validator failures as {field: [messages]}.
  const fieldErrors = data.steam_account_id;
  if (Array.isArray(fieldErrors) && typeof fieldErrors[0] === 'string') {
    return fieldErrors[0];
  }

  return null;
}
