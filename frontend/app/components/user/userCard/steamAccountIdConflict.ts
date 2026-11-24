/** Friend ID collision helpers for the edit-user form.
 *
 * steam_account_id is unique site-wide, so the form warns on blur rather
 * than letting the save fail. The backend returns the same conflict on save
 * as a backstop (409 from the org endpoint, DRF field errors from the global
 * one), which is what steamAccountIdConflictFromError reads. It also reads
 * the Steam lookup refusals (unknown account, rate limit, bad format) so they
 * land on the Friend ID field too.
 */

import { DisplayName } from '~/components/user/avatar';

export interface SteamAccountIdHolder {
  pk: number;
  nickname: string;
  username: string;
}

const SUFFIX = 'Saving will fail until it is freed from that account.';

const FRIEND_ID_ERROR_CODES: ReadonlySet<string> = new Set([
  'steam_account_id_taken',
  'steam_account_not_found',
  'steam_lookup_rate_limited',
  'invalid_friend_id',
]);

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
  const name = DisplayName(holder);
  const who =
    name !== holder.username
      ? // eslint-disable-next-line draftforge/use-display-name -- the @handle identifies the account holding the ID
        `${name} (@${holder.username})`
      : // eslint-disable-next-line draftforge/use-display-name -- the @handle identifies the account holding the ID
        `@${holder.username}`;
  return `Already used by ${who}. ${SUFFIX}`;
}

export function steamAccountIdConflictFromError(body: unknown): string | null {
  if (!body || typeof body !== 'object') return null;
  const data = body as Record<string, unknown>;

  if (
    typeof data.code === 'string' &&
    FRIEND_ID_ERROR_CODES.has(data.code) &&
    typeof data.error === 'string'
  ) {
    return data.error;
  }

  // Global endpoint: DRF renders validator failures as {field: [messages]}.
  const fieldErrors = data.steam_account_id;
  if (Array.isArray(fieldErrors) && typeof fieldErrors[0] === 'string') {
    return fieldErrors[0];
  }

  return null;
}
