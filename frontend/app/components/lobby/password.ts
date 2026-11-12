// Event lobby passwords: one per event, used by every lobby of the event.
// Mirrors backend/lobby/passwords.py, which has the final say.

/** dota_lobby accepts up to 32 characters. */
export const LOBBY_PASSWORD_MAX_LENGTH = 32;

export const LOBBY_PASSWORD_MODES = ['random', 'fixed'] as const;
export type LobbyPasswordMode = (typeof LOBBY_PASSWORD_MODES)[number];

export type LobbyPasswordIssue =
  | 'required'
  | 'too_long'
  | 'invalid_characters'
  | 'surrounding_spaces';

const PRINTABLE_ASCII = /^[\x20-\x7E]*$/;

/** Why a fixed password cannot be used, or null when it can. */
export function lobbyPasswordIssue(value: string | null | undefined): LobbyPasswordIssue | null {
  if (!value) return 'required';
  if (value.length > LOBBY_PASSWORD_MAX_LENGTH) return 'too_long';
  if (!PRINTABLE_ASCII.test(value)) return 'invalid_characters';
  if (value !== value.trim()) return 'surrounding_spaces';
  return null;
}

interface LobbyPasswordValues {
  dota_lobby_password_mode?: LobbyPasswordMode;
  dota_lobby_password?: string;
}

interface IssueContext {
  addIssue: (issue: { code: 'custom'; path: string[]; message: string }) => void;
}

/**
 * zod superRefine for forms holding the password fields: a fixed password
 * must be valid. The message is the issue code; LobbyPasswordSettings shows
 * the translated text.
 */
export function refineLobbyPassword(values: LobbyPasswordValues, ctx: IssueContext): void {
  if (values.dota_lobby_password_mode !== 'fixed') return;
  const issue = lobbyPasswordIssue(values.dota_lobby_password);
  if (issue) ctx.addIssue({ code: 'custom', path: ['dota_lobby_password'], message: issue });
}

/** The password fields to send: a random mode never sends a password. */
export function lobbyPasswordPayload(values: LobbyPasswordValues): LobbyPasswordValues {
  const mode = values.dota_lobby_password_mode ?? 'random';
  return mode === 'fixed'
    ? { dota_lobby_password_mode: mode, dota_lobby_password: values.dota_lobby_password ?? '' }
    : { dota_lobby_password_mode: mode };
}
