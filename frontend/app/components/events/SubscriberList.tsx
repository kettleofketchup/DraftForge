import { useQuery } from '@tanstack/react-query';
import { getRepeaterSubscribers } from '~/components/api/api';
import { UserAvatar } from '~/components/user/UserAvatar';
import { ScrollArea } from '~/components/ui/scroll-area';
import { Badge } from '~/components/ui/badge';
import { Bell } from 'lucide-react';

interface SubscriberListProps {
  repeaterId: number;
}

export function SubscriberList({ repeaterId }: SubscriberListProps) {
  const { data: subscribers, isLoading } = useQuery({
    queryKey: ['repeater-subscribers', repeaterId],
    queryFn: () => getRepeaterSubscribers(repeaterId),
  });

  if (isLoading) return <p className="text-muted-foreground text-sm">Loading...</p>;
  if (!subscribers || subscribers.length === 0) return null;

  const content = (
    <div className="space-y-1.5">
      {subscribers.map((sub) => (
        <div key={sub.id} className="flex items-center gap-2 py-1">
          <UserAvatar
            user={{ nickname: sub.nickname, username: sub.username, discordId: sub.discordId, avatar: sub.avatar }}
            size="sm"
          />
          <span className="text-sm text-foreground">{sub.nickname || sub.username}</span>
        </div>
      ))}
    </div>
  );

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <Bell className="h-4 w-4 text-muted-foreground" />
        <h4 className="text-sm font-semibold text-foreground">Notification Subscribers</h4>
        <Badge variant="secondary" className="text-xs">{subscribers.length}</Badge>
      </div>
      {subscribers.length > 5 ? (
        <ScrollArea className="h-[200px] rounded-lg border border-border p-2">
          {content}
        </ScrollArea>
      ) : (
        <div className="rounded-lg border border-border p-2">
          {content}
        </div>
      )}
    </div>
  );
}
