import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef } from 'react';
import { toast } from 'sonner';
import {
  fetchEventOpsNotices,
  resolveEventOpsNotice,
  type OpsNotice,
} from '~/components/api/opsNoticesAPI';
import { OpsNoticeTable } from '~/components/opsnotices/OpsNoticeTable';
import { Card, CardContent, CardHeader, CardTitle } from '~/components/ui/card';
import { getLogger } from '~/lib/logger';

const log = getLogger('OpsNoticesCard');

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

  const { mutate: resolveMutate } = resolve;
  const onResolve = useCallback(
    (n: OpsNotice) => resolveMutate(n.id),
    [resolveMutate],
  );

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
        <OpsNoticeTable
          notices={data}
          showEvent={false}
          noticeHref={noticeHref}
          onResolve={onResolve}
          resolving={resolve.isPending}
        />
      </CardContent>
    </Card>
  );
}
