import { isAxiosError } from 'axios';
import api from '~/components/api/axios';
import {
  GameLobbyResponseSchema,
  InviteResultSchema,
  type GameLobbyResponse,
  type InviteResult,
} from './schemas';

export interface CreateLobbyOptions {
  allowMissing?: boolean;
  replace?: boolean;
  /** Host the match again although a lobby already played it. */
  replay?: boolean;
}

export type InviteRequest = { missing: true } | { players: number[] } | Record<string, never>;

export async function getGameLobby(gameId: number): Promise<GameLobbyResponse> {
  const response = await api.get(`/games/${gameId}/lobby/`);
  return GameLobbyResponseSchema.parse(response.data);
}

export async function createGameLobby(
  gameId: number,
  options: CreateLobbyOptions = {},
): Promise<void> {
  await api.post(`/games/${gameId}/lobby/`, {
    allow_missing: options.allowMissing ?? false,
    replace: options.replace ?? false,
    replay: options.replay ?? false,
  });
}

export async function closeGameLobby(gameId: number): Promise<GameLobbyResponse> {
  const response = await api.delete(`/games/${gameId}/lobby/`);
  return GameLobbyResponseSchema.parse(response.data);
}

export async function inviteToGameLobby(
  gameId: number,
  body: InviteRequest,
): Promise<InviteResult> {
  const response = await api.post(`/games/${gameId}/lobby/invite/`, body);
  return InviteResultSchema.parse(response.data);
}

export async function launchGameLobby(
  gameId: number,
  force = false,
): Promise<GameLobbyResponse> {
  const response = await api.post(`/games/${gameId}/lobby/launch/`, { force });
  return GameLobbyResponseSchema.parse(response.data);
}

// Organizer-facing text for lobby error codes (dota_lobby problem codes,
// DraftForge eligibility codes and client codes). Unknown codes fall back to
// the server's message.
const ERROR_TEXT: Record<string, string> = {
  league_not_held: "No lobby bot is an admin of this tournament's Dota league.",
  missing_steam_ids: 'Some players have no Steam account linked.',
  missing_steam_id: 'Link your Steam account to get a lobby invite.',
  unavailable: 'No lobby bot is available right now. Try again shortly.',
  gc_timeout: "Dota's game coordinator did not answer. Try again.",
  unreachable: 'The lobby service cannot be reached.',
  not_configured: 'The lobby service is not configured.',
  invite_limited: 'Invite limit reached for now. Try again later.',
  rate_limited: 'Too many lobby requests. Wait a moment and try again.',
  not_ready: 'Not every player is seated and ready.',
  host_not_seated: 'The lobby host is not seated yet.',
  invalid_state: 'The lobby cannot do that in its current state.',
  conflict: 'Another lobby already uses this game.',
  unsupported_game_mode: 'Custom Lobby tournaments cannot get a hosted lobby.',
  unsupported_game_type: 'Only Dota 2 tournaments can get a hosted lobby.',
  unknown_game_mode: "The lobby service does not know this tournament's game mode.",
  unknown_region: "The lobby service does not know this tournament's region.",
  invalid_request: 'The lobby service rejected the request.',
  password_unavailable: 'The lobby password can no longer be derived. Create a new lobby.',
  lobby_disabled: 'Hosted lobbies are turned off.',
  lobby_mode_off: 'Hosted lobbies are off for this tournament.',
  active_lobby_exists: 'This game already has a lobby.',
  lobby_match_played:
    "The lobby's match was played. Confirm the winner, or replay the match if it must be played again.",
  lobby_in_progress: 'The match has started.',
  lobby_not_created: 'The lobby is still being created.',
  no_active_lobby: 'This game has no open lobby.',
  teams_missing: 'Both teams must be set first.',
  same_team: 'Both slots hold the same team.',
  game_not_pending: 'The game is no longer pending.',
  team_too_large: 'A team has more than five players with Steam accounts.',
  no_tournament: 'This game has no tournament.',
};

export function lobbyErrorText(code: string | null | undefined, fallback?: string): string {
  if (code && ERROR_TEXT[code]) return ERROR_TEXT[code];
  return fallback || code || 'Unknown error';
}

/** `{error, code}` from a failed lobby request, as display text. */
export function lobbyRequestErrorText(error: unknown): string {
  if (isAxiosError(error)) {
    const data = error.response?.data as { code?: string; error?: string } | undefined;
    if (data?.code || data?.error) return lobbyErrorText(data.code, data.error);
    return error.message;
  }
  return error instanceof Error ? error.message : 'Unknown error';
}
