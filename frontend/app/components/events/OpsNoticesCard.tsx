import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { formatDistanceToNow } from 'date-fns';
import { useEffect, useRef } from 'react';
import { Link } from 'react-router';
import { toast } from 'sonner';
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

const RESOLVE_ERROR_MESSAGES: Record<string, string> = {
  task_resolve_unsupported: 'task notices close on their own',
};

interface HttpErrorShape {
  message?: string;
  response?: { status?: number; data?: { code?: string; detail?: string } };
}

function reportResolveError(err: unknown): void {
  const e = err as HttpErrorShape;
  if (e?.response?.status === 404) {
    toast.warning('Notice was already resolved');
    return;
  }
  const data = e?.response?.data;
  const msg =
    (data?.code && RESOLVE_ERROR_MESSAGES[data.code]) ||
    data?.detail ||
    data?.code ||
    e?.message ||
    'unknown error';
  toast.error(`Couldn't resolve notice: ${msg}`);
}

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
    onSettled: () => queryClient.invalidateQueries({ queryKey }),
    onError: (err, noticeId) => {
      log.error('Failed to resolve operations notice', { noticeId, err });
      reportResolveError(err);
    },
  });

  const loggedFailure = useRef(false);
  useEffect(() => {
    if (!error) {
      loggedFailure.current = false;
      return;
    }
    if (loggedFailure.current) return;
    loggedFailure.current = true;
    log.error('Failed to load operations notices', { eventId, error });
  }, [error, eventId]);

  if (error && !data) {
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
        {error && (
          <p className="text-sm text-muted-foreground">
            Couldn&apos;t refresh operations notices
          </p>
        )}
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
