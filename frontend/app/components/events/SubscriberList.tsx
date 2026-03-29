import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getRepeaterSubscribers } from '~/components/api/api';
import { UserAvatar } from '~/components/user/UserAvatar';
import { Badge } from '~/components/ui/badge';
import { Bell, ChevronDown, ChevronUp } from 'lucide-react';

interface SubscriberListProps {
  repeaterId: number;
}

export function SubscriberList({ repeaterId }: SubscriberListProps) {
  const [expanded, setExpanded] = useState(false);
  const { data: subscribers, isLoading } = useQuery({
    queryKey: ['repeater-subscribers', repeaterId],
    queryFn: () => getRepeaterSubscribers(repeaterId),
  });

  if (isLoading) return <p className="text-muted-foreground text-sm">Loading...</p>;
  if (!subscribers || subscribers.length === 0) return null;

  return (
    <div>
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 w-full text-left py-1.5 hover:opacity-80 transition-opacity"
      >
        <Bell className="h-4 w-4 text-muted-foreground" />
        <h4 className="text-sm font-semibold text-foreground">Notification Subscribers</h4>
        <Badge variant="secondary" className="text-xs">{subscribers.length}</Badge>
        <span className="ml-auto text-muted-foreground">
          {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </span>
      </button>
      {expanded && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-1 mt-2 rounded-lg border border-border p-2">
          {subscribers.map((sub) => (
            <div key={sub.id} className="flex items-center gap-2 p-1.5 rounded-md hover:bg-muted/40 transition-colors">
              <UserAvatar
                user={{ nickname: sub.nickname, username: sub.username, discordId: sub.discordId, avatar: sub.avatar }}
                size="sm"
              />
              <span className="text-sm text-foreground truncate">
                {sub.nickname || sub.username}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
