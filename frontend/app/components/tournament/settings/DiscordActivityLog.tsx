import { useQuery } from '@tanstack/react-query';
import { formatDistanceToNow } from 'date-fns';
import { CheckCircle, Loader2, XCircle } from 'lucide-react';
import { fetchDiscordTournamentLogs } from '~/components/api/api';
import { DiscordIcon } from '~/components/events/DiscordConfigSection';
import { Badge } from '~/components/ui/badge';
import { ScrollArea } from '~/components/ui/scroll-area';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '~/components/ui/table';

interface Props {
  tournamentId: number;
}

const TYPE_LABELS: Record<string, string> = {
  draft_link: 'Draft Link',
  herodraft_link: 'Hero Draft',
};

export function DiscordActivityLog({ tournamentId }: Props) {
  const { data: logs, isLoading, isError } = useQuery({
    queryKey: ['tournament', tournamentId, 'discord-logs'],
    queryFn: () => fetchDiscordTournamentLogs(tournamentId),
    refetchInterval: 10_000,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12" data-testid="discord-activity-log">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground mr-2" />
        <span className="text-muted-foreground text-sm">Loading activity...</span>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="text-muted-foreground p-4 text-center" data-testid="discord-activity-log">
        Failed to load Discord activity.
      </div>
    );
  }

  if (!logs || logs.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center border border-border rounded-lg bg-base-300/50" data-testid="discord-activity-log">
        <DiscordIcon className="h-8 w-8 text-[#5865F2]/50 mb-3" />
        <p className="text-muted-foreground text-sm">
          No Discord activity yet for this tournament.
        </p>
        <p className="text-muted-foreground/60 text-xs mt-1">
          Activity will appear here when Discord notifications are sent.
        </p>
      </div>
    );
  }

  return (
    <div data-testid="discord-activity-log">
      <ScrollArea className="h-[500px] rounded-lg border border-border bg-base-300/50">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Time</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Message</TableHead>
              <TableHead className="text-center">Recipients</TableHead>
              <TableHead className="text-center">Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {logs.map((log) => (
              <TableRow key={log.id} data-testid={`discord-log-entry-${log.id}`}>
                <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                  {formatDistanceToNow(new Date(log.created_at), { addSuffix: true })}
                </TableCell>
                <TableCell>
                  <Badge variant="outline" className="text-xs bg-[#5865F2]/20 text-[#5865F2] border-[#5865F2]/30">
                    {TYPE_LABELS[log.notification_type] || log.notification_type}
                  </Badge>
                </TableCell>
                <TableCell className="text-sm">{log.message}</TableCell>
                <TableCell className="text-center">
                  <Badge variant="outline" className="text-xs tabular-nums">
                    {log.recipient_count}
                  </Badge>
                </TableCell>
                <TableCell className="text-center">
                  {log.success ? (
                    <CheckCircle className="h-4 w-4 text-success mx-auto" />
                  ) : (
                    <XCircle className="h-4 w-4 text-destructive mx-auto" />
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </ScrollArea>
    </div>
  );
}
