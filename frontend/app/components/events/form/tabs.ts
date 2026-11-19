import {
  CalendarDays,
  Gamepad2,
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
  | 'discord';

export const EVENT_TAB_META: Record<
  EventFormTabValue,
  { label: string; icon?: LucideIcon | typeof DiscordIcon }
> = {
  event: { label: 'Event', icon: CalendarDays },
  tournament: { label: 'Tournament', icon: Trophy },
  lobby: { label: 'Lobby', icon: Gamepad2 },
  approval: { label: 'Approval', icon: ShieldCheck },
  discord: { label: 'Discord', icon: DiscordIcon },
};

/** The event-form tab that renders `field` by default. */
export function eventTabForField(field: string): EventFormTabValue {
  for (const [tab, fields] of Object.entries(EVENT_SECTION_FIELDS)) {
    if (field in fields) return tab as EventFormTabValue;
  }
  if (field.startsWith('discord_')) return 'discord';
  return 'event';
}
