import { useQuery } from '@tanstack/react-query';
import { CheckCircle, XCircle } from 'lucide-react';
import { fetchDiscordTournamentLogs } from '~/components/api/api';
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
  const { data: logs, isLoading } = useQuery({
    queryKey: ['tournament-discord-logs', tournamentId],
    queryFn: () => fetchDiscordTournamentLogs(tournamentId),
    refetchInterval: 10_000,
  });

  if (isLoading) {
    return <div className="text-muted-foreground p-4">Loading activity...</div>;
  }

  if (!logs || logs.length === 0) {
    return (
      <div className="text-muted-foreground p-4 text-center">
        No Discord activity yet for this tournament.
      </div>
    );
  }

  return (
    <ScrollArea className="h-[500px]">
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
            <TableRow key={log.id}>
              <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                {new Date(log.created_at).toLocaleString()}
              </TableCell>
              <TableCell>
                <Badge variant="outline" className="text-xs">
                  {TYPE_LABELS[log.notification_type] || log.notification_type}
                </Badge>
              </TableCell>
              <TableCell className="text-sm">{log.message}</TableCell>
              <TableCell className="text-center">{log.recipient_count}</TableCell>
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
  );
}
