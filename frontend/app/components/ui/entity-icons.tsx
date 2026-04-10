/**
 * Centralized entity icons for consistent use across breadcrumbs, nav, cards, headers.
 *
 * Import: import { ENTITY_ICONS, EntityIcon } from '~/components/ui/entity-icons';
 */

import { Building2, CalendarDays, Repeat, Swords, Trophy } from 'lucide-react';
import type { EntityType } from './entity-breadcrumb';
import { cn } from '~/lib/utils';

export const ENTITY_ICONS: Record<EntityType, typeof Building2> = {
  organization: Building2,
  league: Trophy,
  'event-series': Repeat,
  event: CalendarDays,
  tournament: Swords,
};

interface EntityIconProps {
  type: EntityType;
  className?: string;
  size?: 'xs' | 'sm' | 'md';
}

const SIZE_CLASSES = {
  xs: 'h-3 w-3',
  sm: 'h-4 w-4',
  md: 'h-5 w-5',
} as const;

export function EntityIcon({ type, className, size = 'sm' }: EntityIconProps) {
  const Icon = ENTITY_ICONS[type];
  return <Icon className={cn(SIZE_CLASSES[size], 'shrink-0', className)} />;
}
