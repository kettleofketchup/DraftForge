import { useQuery } from '@tanstack/react-query';
import { getEventDiscordState } from '~/components/api/api';
import type { DiscordEventState } from '~/components/events/schemas';
import { Badge } from '~/components/ui/badge';
import { UserAvatar } from '~/components/user/UserAvatar';

interface DiscordLogSectionProps {
  eventId: number;
}

export function DiscordLogSection({ eventId }: DiscordLogSectionProps) {
  const { data: discordState, isLoading } = useQuery({
    queryKey: ['event-discord', eventId],
    queryFn: () => getEventDiscordState(eventId),
  });

  if (isLoading) {
    return <div className="text-muted-foreground p-4">Loading Discord state...</div>;
  }
  if (!discordState) {
    return <div className="text-muted-foreground p-4">No Discord integration configured for this event.</div>;
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
        <h3 className="text-foreground font-semibold mb-3">Activity Log</h3>
        <div className="space-y-2">
          {discordState.logs.length === 0 && (
            <p className="text-muted-foreground text-sm">No activity yet.</p>
          )}
          {discordState.logs.map((log: DiscordEventState['logs'][number]) => (
            <div
              key={log.id}
              className={`border-l-2 pl-4 py-1 ${
                log.success ? 'border-success' : 'border-error'
              }`}
            >
              <div className="flex items-center gap-2">
                <span className="text-foreground text-sm">{log.action}</span>
                <Badge variant={log.success ? 'default' : 'destructive'} className="text-xs">
                  {log.target_type}
                </Badge>
              </div>
              {log.error_message && (
                <p className="text-error text-xs mt-0.5">{log.error_message}</p>
              )}
              <span className="text-muted-foreground text-xs">
                {new Date(log.created_at).toLocaleString()}
              </span>
            </div>
          ))}
        </div>
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
