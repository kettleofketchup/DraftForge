import {
  CalendarDays,
  Gamepad2,
  ShieldCheck,
  Trophy,
  type LucideIcon,
} from 'lucide-react';
import { DraftSettingsFormSchema } from '~/components/teamdraft/schemas';
import { DiscordIcon } from '../DiscordConfigSection';
import { dotaLobbyConfigSchema } from '../schemas';

export type EventFormTabValue =
  | 'event'
  | 'tournament'
  | 'lobby'
  | 'approval'
  | 'discord';

export const EVENT_TAB_META: Record<
  EventFormTabValue,
  {
    label: string;
    icon?: LucideIcon | typeof DiscordIcon;
    /** Search terms for settings the dialog can't read off a closed tab. */
    keywords: string[];
  }
> = {
  event: {
    label: 'Event',
    icon: CalendarDays,
    keywords: ['name', 'description', 'schedule', 'date', 'time', 'timezone'],
  },
  tournament: {
    label: 'Tournament',
    icon: Trophy,
    keywords: ['bracket', 'draft', 'teams', 'league', 'timer', 'captains'],
  },
  lobby: {
    label: 'Lobby',
    icon: Gamepad2,
    keywords: ['game mode', 'password', 'region', 'steam league', 'dota'],
  },
  approval: {
    label: 'Approval',
    icon: ShieldCheck,
    keywords: ['mmr', 'rank', 'screenshot', 'roll call', 'signup', 'steam'],
  },
  discord: {
    label: 'Discord',
    icon: DiscordIcon,
    keywords: ['channel', 'role', 'announcement', 'reminder', 'notify', 'ping'],
  },
};

const TOURNAMENT_FIELDS = new Set<string>([
  'tournament_name',
  'tournament_league',
  'tournament_type',
  'game_type',
  'people_per_team',
  'number_of_teams',
  'draft_type',
  ...Object.keys(DraftSettingsFormSchema.shape),
]);

const LOBBY_FIELDS = new Set<string>([
  'game_mode',
  'custom_game_name',
  'captains_draft_time',
  'lobby_steam_league_id',
  ...Object.keys(dotaLobbyConfigSchema.shape),
]);

const APPROVAL_FIELDS = new Set<string>([
  'min_mmr',
  'allow_active_mmr',
  'allow_previous_rank',
  'allow_battlecup_rating',
  'discord_require_rank_screenshot',
  'discord_require_battlecup_screenshot',
  'require_steam_id',
  'require_mmr_verified',
  'require_profile_complete',
  'roll_call_enabled',
  'allow_user_signups',
  'roll_call_mode',
]);

/** The event-form tab that renders `field`. */
export function eventTabForField(field: string): EventFormTabValue {
  if (TOURNAMENT_FIELDS.has(field)) return 'tournament';
  if (LOBBY_FIELDS.has(field)) return 'lobby';
  if (APPROVAL_FIELDS.has(field)) return 'approval';
  if (field.startsWith('discord_')) return 'discord';
  return 'event';
}
