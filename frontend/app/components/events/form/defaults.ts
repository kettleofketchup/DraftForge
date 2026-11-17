import type { z } from 'zod';
import {
  DISCORD_CONFIG_DEFAULTS,
  DOTA_LOBBY_CONFIG_DEFAULTS,
  type discordConfigSchema,
  type dotaLobbyConfigSchema,
} from '../schemas';

/** Template field defaults shared by the event, series and create dialogs. */
export const EVENT_TEMPLATE_DEFAULTS = {
  name: '',
  description: '',
  tournament_name: '',
  tournament_type: 'double_elimination',
  game_type: 1,
  draft_type: 'shuffle',
  game_mode: 'normal',
  custom_game_name: '',
  captains_draft_time: 10,
  lobby_steam_league_id: null,
  people_per_team: 5,
  number_of_teams: null,
} as const;

type DiscordKey = keyof typeof DISCORD_CONFIG_DEFAULTS;
export type DiscordConfigFormValues = Required<
  Pick<z.input<typeof discordConfigSchema>, DiscordKey>
>;
export type DotaLobbyFormValues = Required<
  z.input<typeof dotaLobbyConfigSchema>
>;

type Nullable<T> = { [K in keyof T]?: T[K] | null };

/**
 * Every discordConfigSchema key, from `src` or its default. Naming each key
 * matters: a reset that omits a z.boolean() field fails submit silently.
 */
export function discordResetValues(
  src: Nullable<DiscordConfigFormValues> | null | undefined,
): DiscordConfigFormValues {
  const out: Record<string, unknown> = {};
  for (const key of Object.keys(DISCORD_CONFIG_DEFAULTS) as DiscordKey[]) {
    const value = src?.[key] ?? DISCORD_CONFIG_DEFAULTS[key];
    out[key] = Array.isArray(value) ? [...value] : value;
  }
  return out as DiscordConfigFormValues;
}

type DotaLobbySource = Nullable<
  Omit<DotaLobbyFormValues, 'dota_lobby_password' | 'dota_lobby_password_saved'>
>;

/** Lobby reset values; the password itself is write-only, so it starts empty. */
export function dotaLobbyResetValues(
  src: DotaLobbySource | null | undefined,
  { savedFromMode }: { savedFromMode: boolean },
): DotaLobbyFormValues {
  const D = DOTA_LOBBY_CONFIG_DEFAULTS;
  const mode = src?.dota_lobby_password_mode ?? D.dota_lobby_password_mode;
  return {
    dota_lobby_mode: src?.dota_lobby_mode ?? D.dota_lobby_mode,
    dota_lobby_launch: src?.dota_lobby_launch ?? D.dota_lobby_launch,
    dota_lobby_region: src?.dota_lobby_region ?? D.dota_lobby_region,
    discord_send_lobby_info:
      src?.discord_send_lobby_info ?? D.discord_send_lobby_info,
    dota_lobby_password_mode: mode,
    dota_lobby_password: '',
    dota_lobby_password_saved: savedFromMode && mode === 'fixed',
  };
}
