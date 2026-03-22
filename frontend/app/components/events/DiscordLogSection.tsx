import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getEventDiscordState } from '~/components/api/api';
import type { DiscordEventState } from '~/components/events/schemas';
import { LogCategory, LOG_CATEGORY_LABELS } from '~/components/events/schemas';
import { Badge } from '~/components/ui/badge';
import { UserAvatar } from '~/components/user/UserAvatar';
import { ScrollArea } from '~/components/ui/scroll-area';

interface DiscordLogSectionProps {
  eventId: number;
}

const CATEGORY_COLORS: Record<number, string> = {
  [LogCategory.SYSTEM]: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
  [LogCategory.INTERACTION]: 'bg-violet-500/20 text-violet-300 border-violet-500/30',
  [LogCategory.SIGNUP]: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
  [LogCategory.NOTIFICATION]: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
};

const CATEGORY_BORDER: Record<number, string> = {
  [LogCategory.SYSTEM]: 'border-blue-500',
  [LogCategory.INTERACTION]: 'border-violet-500',
  [LogCategory.SIGNUP]: 'border-emerald-500',
  [LogCategory.NOTIFICATION]: 'border-amber-500',
};

export function DiscordLogSection({ eventId }: DiscordLogSectionProps) {
  const { data: discordState, isLoading } = useQuery({
    queryKey: ['event-discord', eventId],
    queryFn: () => getEventDiscordState(eventId),
  });
  const [activeFilter, setActiveFilter] = useState<number | null>(null);

  if (isLoading) {
    return <div className="text-muted-foreground p-4">Loading Discord state...</div>;
  }
  if (!discordState) {
    return <div className="text-muted-foreground p-4">No Discord integration configured for this event.</div>;
  }

  const filteredLogs = activeFilter
    ? discordState.logs.filter((log: DiscordEventState['logs'][number]) => log.category === activeFilter)
    : discordState.logs;

  // Count per category
  const categoryCounts: Record<number, number> = {};
  for (const log of discordState.logs) {
    categoryCounts[log.category] = (categoryCounts[log.category] || 0) + 1;
  }

  return (
    <div className="space-y-6">
      {/* Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <MessageStatusCard
          title="Signup Post"
          message={discordState.signup_message}
          guildId={discordState.guild_id}
        />
        <MessageStatusCard
          title="Announcement"
          message={discordState.announcement}
          guildId={discordState.guild_id}
        />
        <div className="bg-base-300 border border-border rounded-lg p-4">
          <h4 className="text-foreground font-semibold text-sm">Scheduled Event</h4>
          {discordState.scheduled_event_id ? (
            <Badge className="bg-success mt-2">Created</Badge>
          ) : (
            <Badge variant="outline" className="mt-2">Not configured</Badge>
          )}
        </div>
      </div>

      {/* Activity Log */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-foreground font-semibold">Activity Log</h3>
          <span className="text-muted-foreground text-xs">{discordState.logs.length} entries</span>
        </div>

        {/* Category filter tabs */}
        <div className="flex flex-wrap gap-1.5 mb-3">
          <button
            onClick={() => setActiveFilter(null)}
            className={`px-2.5 py-1 text-xs rounded-md transition-colors cursor-pointer ${
              activeFilter === null
                ? 'bg-primary/20 text-primary font-medium'
                : 'bg-muted/30 text-muted-foreground hover:bg-muted/50'
            }`}
          >
            All ({discordState.logs.length})
          </button>
          {Object.entries(LOG_CATEGORY_LABELS).map(([id, label]) => {
            const count = categoryCounts[Number(id)] || 0;
            if (count === 0) return null;
            return (
              <button
                key={id}
                onClick={() => setActiveFilter(Number(id) === activeFilter ? null : Number(id))}
                className={`px-2.5 py-1 text-xs rounded-md transition-colors cursor-pointer ${
                  activeFilter === Number(id)
                    ? CATEGORY_COLORS[Number(id)]
                    : 'bg-muted/30 text-muted-foreground hover:bg-muted/50'
                }`}
              >
                {label} ({count})
              </button>
            );
          })}
        </div>

        {/* Scrollable log list */}
        <ScrollArea className="h-[400px] rounded-lg border border-border bg-base-300/50 p-3">
          <div className="space-y-2">
            {filteredLogs.length === 0 && (
              <p className="text-muted-foreground text-sm py-4 text-center">No activity yet.</p>
            )}
            {filteredLogs.map((log: DiscordEventState['logs'][number]) => (
              <div
                key={log.id}
                className={`border-l-2 pl-3 py-1.5 ${
                  CATEGORY_BORDER[log.category] || (log.success ? 'border-success' : 'border-error')
                }`}
              >
                <div className="flex items-center gap-2 flex-wrap">
                  <Badge
                    variant="outline"
                    className={`text-[10px] px-1.5 py-0 ${CATEGORY_COLORS[log.category] || ''}`}
                  >
                    {log.category_display}
                  </Badge>
                  <span className="text-foreground text-sm font-medium">{log.action}</span>
                  {log.target_type && (
                    <Badge variant="outline" className="text-[10px] px-1.5 py-0 text-muted-foreground">
                      {log.target_type}
                    </Badge>
                  )}
                </div>
                {log.discord_username && (
                  <div className="flex items-center gap-1.5 mt-0.5">
                    <UserAvatar
                      user={{ nickname: log.discord_username, discordId: log.discord_user_id }}
                      size="tiny"
                    />
                    <span className="text-muted-foreground text-xs">{log.discord_username}</span>
                  </div>
                )}
                {log.error_message && (
                  <p className="text-error text-xs mt-0.5">{log.error_message}</p>
                )}
                <span className="text-muted-foreground text-[10px]">
                  {new Date(log.created_at).toLocaleString()}
                </span>
              </div>
            ))}
          </div>
        </ScrollArea>
      </div>

      {/* DM History */}
      {discordState.dms.length > 0 && (
        <div>
          <h3 className="text-foreground font-semibold mb-3">DM History</h3>
          <div className="space-y-2">
            {discordState.dms.map((dm: DiscordEventState['dms'][number]) => (
              <div key={dm.id} className="bg-base-300 rounded p-3 flex items-center gap-3">
                <UserAvatar
                  user={{ nickname: dm.nickname, username: dm.username, discordId: dm.discord_user_id }}
                  size="sm"
                />
                <div className="flex-1">
                  <span className="text-foreground text-sm">{dm.nickname || dm.username}</span>
                  <span className="text-muted-foreground text-xs ml-2">{dm.dm_type_display}</span>
                </div>
                <div className="flex gap-1">
                  {dm.delivered ? (
                    <Badge className="bg-success text-xs">Delivered</Badge>
                  ) : dm.can_send ? (
                    <Badge className="bg-warning text-xs">Pending</Badge>
                  ) : (
                    <Badge variant="destructive" className="text-xs">No Discord</Badge>
                  )}
                  {dm.responded && (
                    <Badge className="bg-info text-xs">Responded</Badge>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function MessageStatusCard({ title, message, guildId }: {
  title: string;
  message: DiscordEventState['signup_message'];
  guildId: string;
}) {
  const discordLink = message?.message_id && guildId
    ? `https://discord.com/channels/${guildId}/${message.thread_id || message.channel_id}/${message.message_id}`
    : null;

  return (
    <div className="bg-base-300 border border-border rounded-lg p-4">
      <h4 className="text-foreground font-semibold text-sm">{title}</h4>
      {message?.has_posted ? (
        <div className="mt-2 space-y-1">
          <Badge className="bg-success">Posted</Badge>
          <p className="text-muted-foreground text-xs">{message.channel_type} channel</p>
          {discordLink && (
            <a href={discordLink} target="_blank" rel="noopener noreferrer"
               className="text-secondary hover:text-secondary-hover text-xs">
              View in Discord →
            </a>
          )}
        </div>
      ) : (
        <Badge variant="outline" className="mt-2">Not posted</Badge>
      )}
    </div>
  );
}
