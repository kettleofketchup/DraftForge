// Event lobby passwords: one per event, used by every lobby of the event.
// Mirrors backend/lobby/passwords.py, which has the final say.

import { GAME_TYPE } from '~/components/game/constants';

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
  /** Lobby settings only apply to Dota 2: other games skip them. */
  game_type?: number;
  dota_lobby_password_mode?: LobbyPasswordMode;
  dota_lobby_password?: string;
  /**
   * The saved setting is already fixed (edit forms): an empty field keeps
   * the saved password, which the API keeps when none is sent.
   */
  dota_lobby_password_saved?: boolean;
}

type LobbyPasswordPayload = Pick<
  LobbyPasswordValues,
  'dota_lobby_password_mode' | 'dota_lobby_password'
>;

const isOtherGame = (values: LobbyPasswordValues): boolean =>
  values.game_type !== undefined && values.game_type !== GAME_TYPE.DOTA2;

const keepsSavedPassword = (values: LobbyPasswordValues): boolean =>
  !values.dota_lobby_password && !!values.dota_lobby_password_saved;

interface IssueContext {
  addIssue: (issue: { code: 'custom'; path: string[]; message: string }) => void;
}

/**
 * zod superRefine for forms holding the password fields: a fixed password
 * must be valid, unless the form is for another game (the section is hidden)
 * or the field is empty and the saved fixed password stays. The message is
 * the issue code; LobbyPasswordSettings shows the translated text.
 */
export function refineLobbyPassword(values: LobbyPasswordValues, ctx: IssueContext): void {
  if (isOtherGame(values) || values.dota_lobby_password_mode !== 'fixed') return;
  if (keepsSavedPassword(values)) return;
  const issue = lobbyPasswordIssue(values.dota_lobby_password);
  if (issue) ctx.addIssue({ code: 'custom', path: ['dota_lobby_password'], message: issue });
}

/**
 * The password fields to send. A random mode never sends a password, nor
 * does a fixed one that keeps its saved password; another game sends
 * neither field, so the saved setting stays.
 */
export function lobbyPasswordPayload(values: LobbyPasswordValues): LobbyPasswordPayload {
  if (isOtherGame(values)) return {};
  const mode = values.dota_lobby_password_mode ?? 'random';
  if (mode !== 'fixed' || keepsSavedPassword(values)) return { dota_lobby_password_mode: mode };
  return { dota_lobby_password_mode: mode, dota_lobby_password: values.dota_lobby_password ?? '' };
}
