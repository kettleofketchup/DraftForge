import { Mail, MailCheck, Pencil, Repeat, Users } from 'lucide-react';
import { Link } from 'react-router';
import { toast } from 'sonner';
import type { EventRepeaterListItem } from '~/components/api/api';
import {
  DAY_LABELS,
  FREQUENCY_SHORT_LABELS,
} from '~/components/events/schemas';
import { Badge } from '~/components/ui/badge';
import { SecondaryButton } from '~/components/ui/buttons';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '~/components/ui/tooltip';
import { useRepeaterSubscriptionMutation } from '~/hooks/useEvent';
import { cn } from '~/lib/utils';
import { useUserStore } from '~/store/userStore';

export function RepeatersList({
  repeaters,
  loading,
  onEdit,
  onDelete,
}: {
  repeaters: EventRepeaterListItem[];
  loading: boolean;
  onEdit?: (repeater: EventRepeaterListItem) => void;
  onDelete?: (repeater: EventRepeaterListItem) => void;
}) {
  const currentUser = useUserStore((state) => state.currentUser);
  const { subscribe, unsubscribe } = useRepeaterSubscriptionMutation();
  const isPending = subscribe.isPending || unsubscribe.isPending;

  if (loading) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        Loading repeating events...
      </div>
    );
  }
  if (repeaters.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        No repeating events found
      </div>
    );
  }
  return (
    <div>
      <h3 className="text-lg font-semibold mb-3 hidden lg:block">
        <Repeat className="inline h-4 w-4 mr-1.5 align-text-bottom" />
        Repeating Events ({repeaters.length})
      </h3>
      <div className="grid gap-2">
        {repeaters.map((r) => (
          <Link
            key={r.id}
            to={`/event-series/${r.id}`}
            className="flex items-center gap-3 rounded-lg p-3 border border-border/50 bg-muted/25 hover:bg-muted/45 transition-colors cursor-pointer"
            data-testid={`repeater-strip-${r.id}`}
          >
            {/* Icon block */}
            <div className="shrink-0 text-center w-12">
              <Repeat className="h-5 w-5 mx-auto text-muted-foreground" />
              <p className="text-[10px] text-muted-foreground mt-0.5">
                {FREQUENCY_SHORT_LABELS[r.frequency] ?? r.frequency.slice(0, 4)}
              </p>
            </div>

            {/* Info */}
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <p className="font-medium truncate text-sm">{r.name}</p>
                <Badge
                  variant={r.is_active ? 'default' : 'secondary'}
                  className="shrink-0 text-[10px] px-1.5 py-0"
                >
                  {r.is_active ? 'Active' : 'Paused'}
                </Badge>
              </div>
              <div className="flex items-center gap-3 mt-0.5 text-xs text-muted-foreground">
                {r.day_of_week != null && (
                  <span>{DAY_LABELS[r.day_of_week]?.slice(0, 3)}</span>
                )}
                {r.time_of_day && <span>{r.time_of_day?.slice(0, 5)}</span>}
                <span className="inline-flex items-center gap-0.5">
                  <Users className="h-3 w-3" />
                  {r.subscriber_count}
                </span>
              </div>
            </div>

            {/* Action buttons */}
            <div className="flex items-center gap-1 shrink-0">
              {currentUser && r.discord_notify_new_events && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <SecondaryButton
                      size="icon"
                      className={cn(
                        'size-9',
                        r.is_subscribed && 'text-interactive',
                      )}
                      disabled={isPending}
                      aria-label={r.is_subscribed ? 'Unsubscribe' : 'Subscribe'}
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        if (r.is_subscribed) {
                          unsubscribe.mutate(r.id, {
                            onError: () => toast.error('Failed to unsubscribe'),
                          });
                        } else {
                          subscribe.mutate(r.id, {
                            onSuccess: () => toast.success('Subscribed'),
                            onError: () => toast.error('Failed to subscribe'),
                          });
                        }
                      }}
                    >
                      {r.is_subscribed ? (
                        <MailCheck className="h-3.5 w-3.5" />
                      ) : (
                        <Mail className="h-3.5 w-3.5" />
                      )}
                    </SecondaryButton>
                  </TooltipTrigger>
                  <TooltipContent>
                    {r.is_subscribed ? 'Unsubscribe' : 'Subscribe'}
                  </TooltipContent>
                </Tooltip>
              )}
              {onEdit && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <SecondaryButton
                      size="icon"
                      className="size-9"
                      aria-label="Edit series"
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        onEdit(r);
                      }}
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </SecondaryButton>
                  </TooltipTrigger>
                  <TooltipContent>Edit series</TooltipContent>
                </Tooltip>
              )}
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
