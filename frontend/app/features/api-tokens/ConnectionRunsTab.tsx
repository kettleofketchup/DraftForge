import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef } from 'react';

import { SecondaryButton } from '~/components/ui/buttons';
import { DataTable } from '~/components/ui/data-table';
import { Skeleton } from '~/components/ui/skeleton';
import type { OrgFeatureAccess } from '~/features/org-features';
import { extractApiError } from '~/lib/apiError';
import { relativeTime } from './apiTokenColumns';
import {
  isActiveRun,
  useConnectionRun,
  useConnectionRuns,
} from './connectionQueries';
import { connectionKeys } from './connectionQueryKeys';
import {
  RunCounters,
  RunStateBadge,
  makeConnectionRunColumns,
  runKindLabel,
} from './connectionRunColumns';
import {
  connectionErrorMessage,
  type ConnectionRun,
} from './connectionSchemas';

export interface ConnectionRunsTabProps {
  orgId: number;
  access: OrgFeatureAccess;
  connectionId: number;
  selectedRunId: string | null;
  onSelectRun: (runId: string | null) => void;
}

export function ConnectionRunsTab({
  orgId,
  access,
  connectionId,
  selectedRunId,
  onSelectRun,
}: ConnectionRunsTabProps) {
  const runs = useConnectionRuns(orgId, access, connectionId);
  const columns = useMemo(
    () =>
      makeConnectionRunColumns({
        testIdPrefix: 'api-connection-run',
        onView: (run) => onSelectRun(run.id),
      }),
    [onSelectRun],
  );
  return (
    <div className="flex flex-col gap-6" data-testid="api-connection-runs-tab">
      {selectedRunId && (
        <RunDetail
          orgId={orgId}
          access={access}
          connectionId={connectionId}
          runId={selectedRunId}
          onClose={() => onSelectRun(null)}
        />
      )}
      <section
        className="flex flex-col gap-2"
        aria-labelledby="api-connection-runs-heading"
      >
        <h3
          id="api-connection-runs-heading"
          className="text-base font-semibold"
        >
          Run history
        </h3>
        <p className="text-xs text-muted-foreground">
          Runs are kept for 90 days and show counts and fixed codes only, never
          raw responses.
        </p>
        {runs.isLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : runs.isError ? (
          <p role="alert" className="text-sm text-destructive">
            {extractApiError(runs.error) ?? 'Failed to load runs'}
          </p>
        ) : (
          <>
            <DataTable
              columns={columns}
              data={runs.data?.items ?? []}
              getRowId={(r) => r.id}
              getRowTestId={(r) => `api-connection-run-row-${r.id}`}
              initialSorting={[{ id: 'created', desc: true }]}
              emptyMessage="No runs yet"
              data-testid="api-connection-runs-table"
            />
            {runs.data?.next_cursor && (
              <p className="text-xs text-muted-foreground">
                Showing the latest 50 runs.
              </p>
            )}
          </>
        )}
      </section>
    </div>
  );
}

function RunDetail({
  orgId,
  access,
  connectionId,
  runId,
  onClose,
}: {
  orgId: number;
  access: OrgFeatureAccess;
  connectionId: number;
  runId: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const query = useConnectionRun(orgId, access, connectionId, runId);
  const run = query.data;
  const wasActive = useRef(false);
  const active = isActiveRun(run?.state);
  useEffect(() => {
    if (active) {
      wasActive.current = true;
      return;
    }
    if (run && wasActive.current) {
      wasActive.current = false;
      void queryClient.invalidateQueries({
        queryKey: connectionKeys.runs(orgId, access.viewerPk, connectionId),
      });
      void queryClient.invalidateQueries({
        queryKey: connectionKeys.list(orgId, access.viewerPk),
        exact: true,
      });
      void queryClient.invalidateQueries({
        queryKey: connectionKeys.detail(orgId, access.viewerPk, connectionId),
        exact: true,
      });
    }
  }, [active, run, queryClient, orgId, access.viewerPk, connectionId]);

  return (
    <section
      className="flex flex-col gap-3 rounded-md border border-border p-3"
      aria-labelledby="api-connection-run-detail-heading"
      data-testid="api-connection-run-detail"
    >
      <div className="flex items-start justify-between gap-2">
        <h3
          id="api-connection-run-detail-heading"
          className="text-base font-semibold"
        >
          {run ? runKindLabel(run) : 'Run'}
        </h3>
        <SecondaryButton
          type="button"
          size="sm"
          className="min-h-11 sm:min-h-8"
          onClick={onClose}
          data-testid="api-connection-run-detail-close"
        >
          Close
        </SecondaryButton>
      </div>
      {query.isLoading && <Skeleton className="h-16 w-full" />}
      {query.isError && (
        <p role="alert" className="text-sm text-destructive">
          {extractApiError(query.error) ?? 'Failed to load the run'}
        </p>
      )}
      {run && <RunBody run={run} />}
    </section>
  );
}

function RunBody({ run }: { run: ConnectionRun }) {
  return (
    <>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <RunStateBadge state={run.state} testId="api-connection-run-state" />
        <span className="text-muted-foreground">
          started {relativeTime(run.created_at)}
          {run.finished_at ? `, finished ${relativeTime(run.finished_at)}` : ''}
        </span>
      </div>
      <p
        className="sr-only"
        aria-live="polite"
        data-testid="api-connection-run-live"
      >
        Run {run.state}
      </p>
      {run.worker_status && (
        <p
          className="text-sm text-warning"
          data-testid="api-connection-run-worker"
        >
          {connectionErrorMessage(run.worker_status)}
        </p>
      )}
      {run.health_only && (
        <p className="text-xs text-muted-foreground">
          Health check only: DraftForge called GET /health and sent no member or
          contact data.
        </p>
      )}
      <RunCounters run={run} />
      {run.issues && run.issues.length > 0 && (
        <div className="flex flex-col gap-1">
          <span className="text-sm font-medium">
            Issues ({run.issue_count})
          </span>
          <ul
            className="flex flex-col gap-1 text-xs"
            data-testid="api-connection-run-issues"
          >
            {run.issues.map((issue, i) => (
              <li key={i} className="wrap-anywhere">
                {connectionErrorMessage(issue.code)}
                {issue.page != null && ` Page ${issue.page}`}
                {issue.index != null && `, row ${issue.index}`}
                {issue.player_id != null && ` (player ${issue.player_id})`}
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}
