import type { z } from 'zod';
import {
  DISCORD_CONFIG_DEFAULTS,
  DOTA_LOBBY_CONFIG_DEFAULTS,
  READY_CHECK_CONFIG_DEFAULTS,
  type discordConfigSchema,
  type dotaLobbyConfigSchema,
  type ReadyCheckFields,
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

/** Every readyCheckConfigSchema key, from `src` or its default; a null chase stays null. */
export function readyCheckResetValues(
  src: Partial<ReadyCheckFields> | null | undefined,
): ReadyCheckFields {
  const D = READY_CHECK_CONFIG_DEFAULTS;
  return {
    roll_call_enabled: src?.roll_call_enabled ?? D.roll_call_enabled,
    roll_call_mode: src?.roll_call_mode ?? D.roll_call_mode,
    auto_confirm: src?.auto_confirm ?? D.auto_confirm,
    ready_check_scope: src?.ready_check_scope ?? D.ready_check_scope,
    ready_check_open_minutes:
      src?.ready_check_open_minutes ?? D.ready_check_open_minutes,
    ready_check_escalation_minutes:
      src?.ready_check_escalation_minutes ?? D.ready_check_escalation_minutes,
    ready_check_close_minutes:
      src?.ready_check_close_minutes ?? D.ready_check_close_minutes,
    ready_check_chase_minutes:
      src?.ready_check_chase_minutes === undefined
        ? D.ready_check_chase_minutes
        : src.ready_check_chase_minutes,
    ready_check_min_completion_pct:
      src?.ready_check_min_completion_pct ?? D.ready_check_min_completion_pct,
    ready_check_low_completion_action:
      src?.ready_check_low_completion_action ??
      D.ready_check_low_completion_action,
    ready_check_notify_on_signup:
      src?.ready_check_notify_on_signup ?? D.ready_check_notify_on_signup,
    ready_check_drop_notice:
      src?.ready_check_drop_notice ?? D.ready_check_drop_notice,
    start_cull_enabled: src?.start_cull_enabled ?? D.start_cull_enabled,
    start_cull_minutes_after:
      src?.start_cull_minutes_after ?? D.start_cull_minutes_after,
    post_cull_fill_mode: src?.post_cull_fill_mode ?? D.post_cull_fill_mode,
    event_voice_channel_id:
      src?.event_voice_channel_id ?? D.event_voice_channel_id,
    voice_presence_confirms:
      src?.voice_presence_confirms ?? D.voice_presence_confirms,
  };
}
