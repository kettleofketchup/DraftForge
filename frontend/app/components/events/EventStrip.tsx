import { Repeat, Users } from 'lucide-react';
import { Link } from 'react-router';
import { Button } from '~/components/ui/button';
import { EditIconButton } from '~/components/ui/buttons';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '~/components/ui/tooltip';
import { cn } from '~/lib/utils';
import { EventStateBadge } from './EventStateBadge';
import { GameType, type EventType } from './schemas';

const GAME_LABELS: Record<number, string> = {
  [GameType.DOTA2]: 'Dota 2',
  [GameType.DEADLOCK]: 'Deadlock',
};

interface EventStripProps {
  event: EventType;
  onEdit?: (event: EventType) => void;
  onEditSeries?: (repeaterId: number) => void;
  className?: string;
}

export function EventStrip({ event, onEdit, onEditSeries, className }: EventStripProps) {
  return (
    <Link
      to={`/events/${event.id}`}
      className={cn(
        'flex items-center gap-3 rounded-lg p-3 border border-border/50 bg-muted/25 hover:bg-muted/45 transition-colors cursor-pointer',
        className,
      )}
      data-testid={`event-strip-${event.id}`}
    >
      {/* Date block */}
      <div className="shrink-0 text-center w-12">
        <p className="text-xs font-medium text-muted-foreground uppercase">
          {new Date(event.scheduled_at).toLocaleDateString(undefined, { month: 'short' })}
        </p>
        <p className="text-lg font-bold leading-tight">
          {new Date(event.scheduled_at).getDate()}
        </p>
      </div>

      {/* Info */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="font-medium truncate text-sm">{event.name}</p>
          <EventStateBadge state={event.state} className="shrink-0" />
        </div>
        <div className="flex items-center gap-3 mt-0.5 text-xs text-muted-foreground">
          <span>
            {new Date(event.scheduled_at).toLocaleTimeString(undefined, {
              hour: 'numeric',
              minute: '2-digit',
            })}
          </span>
          <span>{GAME_LABELS[event.game_type] ?? 'Unknown'}</span>
          <span className="inline-flex items-center gap-0.5">
            <Users className="h-3 w-3" />
            {event.signup_count}/{event.confirmed_count}
          </span>
        </div>
      </div>

      {/* Action buttons */}
      {(onEdit || onEditSeries) && (
        <div className="flex items-center gap-1 shrink-0">
          {onEdit && (
            <EditIconButton
              tooltip="Edit this event"
              onClick={(e) => { e.preventDefault(); e.stopPropagation(); onEdit(event); }}
              data-testid={`event-edit-${event.id}`}
            />
          )}
          {onEditSeries && event.event_repeater && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8"
                  onClick={(e) => { e.preventDefault(); e.stopPropagation(); onEditSeries(event.event_repeater!); }}
                  data-testid={`event-edit-series-${event.id}`}
                >
                  <Repeat className="h-3.5 w-3.5" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Edit series (future events)</TooltipContent>
            </Tooltip>
          )}
        </div>
      )}
    </Link>
  );
}
