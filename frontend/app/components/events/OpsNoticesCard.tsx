import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { formatDistanceToNow } from 'date-fns';
import { useEffect } from 'react';
import { Link } from 'react-router';
import {
  fetchEventOpsNotices,
  resolveEventOpsNotice,
  type OpsNotice,
} from '~/components/api/opsNoticesAPI';
import { Badge } from '~/components/ui/badge';
import { SecondaryButton } from '~/components/ui/buttons';
import { Card, CardContent, CardHeader, CardTitle } from '~/components/ui/card';
import { getLogger } from '~/lib/logger';
import type { NoticeSeverity } from '~/lib/opsnotices/noticeTypes.generated';

const log = getLogger('OpsNoticesCard');

const SEVERITY_VARIANT: Record<
  NoticeSeverity,
  'destructive' | 'secondary' | 'outline'
> = {
  critical: 'destructive',
  warning: 'secondary',
  info: 'outline',
};

export interface OpsNoticesCardProps {
  eventId: number;
  noticeHref?: (n: OpsNotice) => string;
}

export function OpsNoticesCard({ eventId, noticeHref }: OpsNoticesCardProps) {
  const queryClient = useQueryClient();
  const queryKey = ['event-ops-notices', eventId, 'open'];
  const { data, error } = useQuery({
    queryKey,
    queryFn: () =>
      fetchEventOpsNotices(eventId, {
        state: 'open',
        category: ['urgent', 'task'],
      }),
    refetchInterval: 15_000,
  });
  const resolve = useMutation({
    mutationFn: (noticeId: number) => resolveEventOpsNotice(eventId, noticeId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey }),
    onError: (err, noticeId) =>
      log.error('Failed to resolve operations notice', { noticeId, err }),
  });

  useEffect(() => {
    if (error)
      log.error('Failed to load operations notices', { eventId, error });
  }, [error, eventId]);

  if (error) {
    return (
      <p className="mb-4 text-sm text-muted-foreground">
        Couldn&apos;t load operations notices
      </p>
    );
  }
  if (!data?.length) return null;

  return (
    <Card className="mb-4" data-testid="ops-notices-card">
      <CardHeader>
        <CardTitle>Operations notices ({data.length} open)</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {data.map((notice) => (
          <div
            key={notice.id}
            data-testid={`ops-notice-row-${notice.id}`}
            className="flex flex-wrap items-center gap-2 text-sm"
          >
            <Badge variant={SEVERITY_VARIANT[notice.severity]}>
              {notice.severity}
            </Badge>
            <Badge variant="outline">{notice.category}</Badge>
            <span className="min-w-0 flex-1 break-words">
              {noticeHref ? (
                <Link to={noticeHref(notice)} className="hover:underline">
                  {notice.summary}
                </Link>
              ) : (
                notice.summary
              )}
            </span>
            {notice.event_name && (
              <span className="text-muted-foreground">{notice.event_name}</span>
            )}
            {notice.occurrences > 1 && (
              <span className="text-muted-foreground">
                x{notice.occurrences}
              </span>
            )}
            <span className="text-muted-foreground">
              {formatDistanceToNow(new Date(notice.last_seen_at), {
                addSuffix: true,
              })}
            </span>
            {notice.category === 'urgent' && (
              <SecondaryButton
                size="sm"
                data-testid={`ops-notice-resolve-${notice.id}`}
                disabled={resolve.isPending}
                onClick={() => resolve.mutate(notice.id)}
              >
                Resolve
              </SecondaryButton>
            )}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
