import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Eye } from 'lucide-react';
import { getEventDiscordState } from '~/components/api/api';
import type { DiscordEventState } from '~/components/events/schemas';
import { LogCategory, LOG_CATEGORY_LABELS } from '~/components/events/schemas';
import { Badge } from '~/components/ui/badge';
import { Button } from '~/components/ui/button';
import { UserStrip } from '~/components/user';
import { UserAvatar } from '~/components/user/UserAvatar';
import { DisplayName } from '~/components/user/avatar';
import { ScrollArea } from '~/components/ui/scroll-area';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import { TaskScheduleSection } from './TaskScheduleSection';
import { DiscordLogDetailModal } from './DiscordLogDetailModal';

interface DiscordLogSectionProps {
  eventId: number;
  isAdmin?: boolean;
  eventTimezone?: string;
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

export function DiscordLogSection({ eventId, isAdmin, eventTimezone }: DiscordLogSectionProps) {
  const { data: discordState, isLoading } = useQuery({
    queryKey: ['event-discord', eventId],
    queryFn: () => getEventDiscordState(eventId),
    refetchInterval: 15_000,
  });
  const [activeFilter, setActiveFilter] = useState<number | null>(null);
  const [selectedLog, setSelectedLog] = useState<DiscordEventState['logs'][number] | null>(null);

  // Merge DMs into activity log as synthetic NOTIFICATION entries
  // (must be before early returns to keep hook order stable)
  const allLogs = useMemo(() => {
    if (!discordState) return [];
    const dmLogs: DiscordEventState['logs'] = discordState.dms.map(
      (dm: DiscordEventState['dms'][number]) => ({
      id: -dm.id,
      category: LogCategory.NOTIFICATION,
      category_display: 'Notification',
      action: `DM: ${dm.dm_type_display}`,
      target_type: dm.nickname || dm.username || '',
      discord_user_id: dm.discord_user_id || '',
      discord_username: dm.nickname || dm.username || '',
      nickname: dm.nickname,
      username: dm.username,
      avatar: dm.avatar,
      message_id: dm.message_id || null,
      status_code: null,
      error_message: dm.delivered ? '' : (dm.can_send ? 'Pending delivery' : 'User has no Discord'),
      success: dm.delivered,
      created_at: dm.sent_at || dm.created_at,
    }));
    return [...discordState.logs, ...dmLogs].sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    );
  }, [discordState?.logs, discordState?.dms]);

  if (isLoading) {
    return <div className="text-muted-foreground p-4">Loading Discord state...</div>;
  }
  if (!discordState) {
    return <div className="text-muted-foreground p-4">No Discord integration configured for this event.</div>;
  }

  const filteredLogs = activeFilter
    ? allLogs.filter((log) => log.category === activeFilter)
    : allLogs;

  // Count per category
  const categoryCounts: Record<number, number> = {};
  for (const log of allLogs) {
    categoryCounts[log.category] = (categoryCounts[log.category] || 0) + 1;
  }

  return (
    <div className="space-y-6">
      {/* Status Cards — ALWAYS VISIBLE (above tabs) */}
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

      {/* Sub-tabs for different views — flex-wrap + short labels at <sm
          so all three tabs fit at iPhone-SE (320px) without horizontal
          overflow. Full labels return at sm+. */}
      <Tabs defaultValue="schedule">
        <TabsList className="flex-wrap w-full sm:w-fit">
          <TabsTrigger value="schedule" data-testid="discord-subtab-schedule">
            <span className="sm:hidden">Tasks</span>
            <span className="hidden sm:inline">Task Schedule</span>
          </TabsTrigger>
          <TabsTrigger value="activity" data-testid="discord-subtab-activity">
            <span className="sm:hidden">Logs ({allLogs.length})</span>
            <span className="hidden sm:inline">Activity Log ({allLogs.length})</span>
          </TabsTrigger>
          <TabsTrigger value="dms" data-testid="discord-subtab-dms">
            <span className="sm:hidden">DMs ({discordState.dms.length})</span>
            <span className="hidden sm:inline">DM History ({discordState.dms.length})</span>
          </TabsTrigger>
        </TabsList>

        {/* Task Schedule */}
        <TabsContent value="schedule">
          <TaskScheduleSection eventId={eventId} isAdmin={isAdmin} eventTimezone={eventTimezone} />
        </TabsContent>

        {/* Activity Log */}
        <TabsContent value="activity">
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
              All ({allLogs.length})
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

          {/* Scrollable log list — clickable entries */}
          <ScrollArea className="h-[400px] rounded-lg border border-border bg-base-300/50 p-3">
            <div className="space-y-2">
              {filteredLogs.length === 0 && (
                <p className="text-muted-foreground text-sm py-4 text-center">No activity yet.</p>
              )}
              {filteredLogs.map((log: DiscordEventState['logs'][number]) => (
                <div
                  key={log.id}
                  data-testid={`discord-log-entry-${log.id}`}
                  className={`border-l-2 pl-3 py-1.5 cursor-pointer hover:bg-base-400/30 rounded-r transition-colors ${
                    CATEGORY_BORDER[log.category] || (log.success ? 'border-success' : 'border-error')
                  }`}
                  onClick={() => setSelectedLog(log)}
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
                  {log.discord_username && (() => {
                    const logUser = {
                      nickname: log.nickname ?? log.discord_username,
                      username: log.username,
                      avatar: log.avatar,
                      discordId: log.discord_user_id,
                    };
                    return (
                      <div className="flex items-center gap-1.5 mt-0.5">
                        <UserAvatar user={logUser} size="tiny" />
                        <span className="text-muted-foreground text-xs">
                          {DisplayName(logUser)}
                        </span>
                      </div>
                    );
                  })()}
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
        </TabsContent>

        {/* DM History */}
        <TabsContent value="dms">
          <div className="space-y-1">
            {discordState.dms.map((dm: DiscordEventState['dms'][number]) => (
              <UserStrip
                key={dm.id}
                user={{
                  nickname: dm.nickname,
                  username: dm.username,
                  discordId: dm.discord_user_id,
                }}
                compact
                showPositions={false}
                showMmr={false}
                contextSlot={
                  <div className="flex flex-wrap items-center justify-end gap-1">
                    <Badge variant="outline" className="text-[10px] px-1.5 py-0">{dm.dm_type_display}</Badge>
                    {dm.delivered ? (
                      <Badge className="bg-success/20 text-success border-success/30 text-[10px] px-1.5 py-0">Delivered</Badge>
                    ) : dm.can_send ? (
                      <Badge className="bg-warning/20 text-warning border-warning/30 text-[10px] px-1.5 py-0">Pending</Badge>
                    ) : (
                      <Badge variant="destructive" className="text-[10px] px-1.5 py-0">No Discord</Badge>
                    )}
                    {dm.responded && (
                      <Badge className="bg-info/20 text-info border-info/30 text-[10px] px-1.5 py-0">Responded</Badge>
                    )}
                  </div>
                }
                actionSlot={
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 px-2"
                    onClick={() => setSelectedLog({
                      id: dm.id,
                      action: `DM: ${dm.dm_type_display}`,
                      target_type: dm.nickname || dm.username || '',
                      success: dm.delivered,
                      message_id: dm.message_id || null,
                      status_code: null,
                      discord_user_id: dm.discord_user_id || '',
                      discord_username: dm.nickname || dm.username || '',
                      nickname: dm.nickname,
                      username: dm.username,
                      avatar: dm.avatar,
                      error_message: !dm.delivered && !dm.can_send ? 'User has no Discord ID' : '',
                      created_at: dm.sent_at || dm.created_at,
                      category: LogCategory.NOTIFICATION,
                      category_display: 'Notification',
                    })}
                    title="View DM details"
                  >
                    <Eye className="h-3.5 w-3.5" />
                  </Button>
                }
              />
            ))}
            {discordState.dms.length === 0 && (
              <p className="text-muted-foreground text-sm py-4 text-center">No DMs sent yet.</p>
            )}
          </div>
        </TabsContent>
      </Tabs>

      {/* Log Detail Modal */}
      <DiscordLogDetailModal
        log={selectedLog}
        open={!!selectedLog}
        onOpenChange={(open) => !open && setSelectedLog(null)}
        repeaterName={discordState.event_repeater_name}
      />
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
