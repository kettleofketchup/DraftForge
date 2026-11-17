import { CreateTournamentSchema, type CreateTournamentInput } from '../schemas';

export type FormTab = 'general' | 'config' | 'discord';

const CONFIG_FIELDS = new Set([
  'game_mode',
  'lobby_steam_league_id',
  'captains_draft_time',
  'custom_game_name',
  'auto_create_hero_drafts',
  'dota_lobby_mode',
  'dota_lobby_launch',
  'dota_lobby_region',
  'draft_timer_enabled',
  'draft_grace_time_s',
  'draft_reserve_time_s',
  'draft_timeout_action',
  'hero_timer_enabled',
  'hero_grace_time_s',
  'hero_reserve_time_s',
]);

const DRAFT_OPTION_FIELDS: Record<string, string> = {
  timer_enabled: 'draft_timer_enabled',
  grace_time_ms: 'draft_grace_time_s',
  reserve_time_ms: 'draft_reserve_time_s',
  hero_timer_enabled: 'hero_timer_enabled',
  hero_grace_time_ms: 'hero_grace_time_s',
  hero_reserve_time_ms: 'hero_reserve_time_s',
};

const DISCORD_FIELDS = new Set([
  'discord_send_draft_link',
  'discord_send_herodraft_link',
  'discord_send_lobby_info',
]);

const FORM_FIELDS = new Set(Object.keys(CreateTournamentSchema.shape));

export function tabForField(field: string): FormTab {
  if (CONFIG_FIELDS.has(field)) return 'config';
  if (DISCORD_FIELDS.has(field)) return 'discord';
  return 'general';
}

export function fieldErrorsFrom(
  data: unknown,
): { field: keyof CreateTournamentInput; message: string }[] {
  if (!data || typeof data !== 'object' || Array.isArray(data)) return [];
  const out: { field: keyof CreateTournamentInput; message: string }[] = [];
  const { draft_options: nested, ...top } = data as Record<string, unknown>;
  const entries = Object.entries(top);
  if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
    for (const [key, value] of Object.entries(nested)) {
      if (DRAFT_OPTION_FIELDS[key])
        entries.push([DRAFT_OPTION_FIELDS[key], value]);
    }
  }
  for (const [key, value] of entries) {
    const field = key === 'league_id_write' ? 'league' : key;
    if (!FORM_FIELDS.has(field)) continue;
    const message = Array.isArray(value)
      ? value.map(String).join(' ')
      : String(value);
    if (!message) continue;
    out.push({ field: field as keyof CreateTournamentInput, message });
  }
  return out;
}
