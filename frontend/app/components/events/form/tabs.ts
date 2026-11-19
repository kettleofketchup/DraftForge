import {
  CalendarDays,
  Gamepad2,
  ListChecks,
  ShieldCheck,
  Trophy,
  type LucideIcon,
} from 'lucide-react';
import { DiscordIcon } from '../DiscordConfigSection';
import { EVENT_SECTION_FIELDS } from './settingsFields';

export type EventFormTabValue =
  | 'event'
  | 'tournament'
  | 'lobby'
  | 'approval'
  | 'ready'
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
  ready: {
    label: 'Ready check',
    icon: ListChecks,
    keywords: ['ready', 'rsvp', 'confirmation', 'cull', 'voice', 'roll call'],
  },
  discord: {
    label: 'Discord',
    icon: DiscordIcon,
    keywords: ['channel', 'role', 'announcement', 'reminder', 'notify', 'ping'],
  },
};

export const READY_CHECK_FIELDS = new Set<string>(
  Object.keys(EVENT_SECTION_FIELDS.ready),
);

/** The event-form tab that renders `field` by default. */
export function eventTabForField(field: string): EventFormTabValue {
  for (const [tab, fields] of Object.entries(EVENT_SECTION_FIELDS)) {
    if (field in fields) return tab as EventFormTabValue;
  }
  if (field.startsWith('discord_')) return 'discord';
  return 'event';
}
