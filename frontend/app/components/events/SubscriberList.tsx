import { useQuery } from '@tanstack/react-query';
import { Bell, ChevronDown, ChevronUp } from 'lucide-react';
import { useState } from 'react';
import { getRepeaterSubscribers } from '~/components/api/api';
import { Badge } from '~/components/ui/badge';
import { DisplayName } from '~/components/user/avatar';
import { UserAvatar } from '~/components/user/UserAvatar';
import { repeaterKeys } from '~/hooks/useEvent';

interface SubscriberListProps {
  repeaterId: number;
}

export function SubscriberList({ repeaterId }: SubscriberListProps) {
  const [expanded, setExpanded] = useState(false);
  const { data: subscribers, isLoading } = useQuery({
    queryKey: repeaterKeys.subscribers(repeaterId),
    queryFn: () => getRepeaterSubscribers(repeaterId),
  });

  if (isLoading)
    return <p className="text-muted-foreground text-sm">Loading...</p>;
  if (!subscribers || subscribers.length === 0) return null;

  return (
    <div>
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 w-full text-left py-1.5 hover:opacity-80 transition-opacity"
      >
        <Bell className="h-4 w-4 text-muted-foreground" />
        <h4 className="text-sm font-semibold text-foreground">
          Notification Subscribers
        </h4>
        <Badge variant="secondary" className="text-xs">
          {subscribers.length}
        </Badge>
        <span className="ml-auto text-muted-foreground">
          {expanded ? (
            <ChevronUp className="h-4 w-4" />
          ) : (
            <ChevronDown className="h-4 w-4" />
          )}
        </span>
      </button>
      {expanded && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-1 mt-2 rounded-lg border border-border p-2">
          {subscribers.map(({ id, ...subscriber }) => (
            <div
              key={id}
              className="flex items-center gap-2 p-1.5 rounded-md hover:bg-muted/40 transition-colors"
            >
              {/* id is the subscription's, not the user's pk, so it stays out of the cache lookup */}
              <UserAvatar user={subscriber} size="sm" />
              <span className="text-sm text-foreground truncate">
                {DisplayName(subscriber)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
