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
]);

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
  for (const [key, value] of Object.entries(data as Record<string, unknown>)) {
    const field = key === 'league_id_write' ? 'league' : key;
    if (!FORM_FIELDS.has(field)) continue;
    const message = Array.isArray(value) ? value.map(String).join(' ') : String(value);
    if (!message) continue;
    out.push({ field: field as keyof CreateTournamentInput, message });
  }
  return out;
}
