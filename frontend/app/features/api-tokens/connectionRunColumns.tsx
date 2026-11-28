import { Badge } from '~/components/ui/badge';
import { SecondaryButton } from '~/components/ui/buttons';
import {
  DataTableColumnHeader,
  type AppColumnDef,
} from '~/components/ui/data-table';
import { relativeTime } from './apiTokenColumns';
import {
  connectionErrorMessage,
  type ConnectionRun,
  type RunState,
  type RunSummary,
} from './connectionSchemas';

type BadgeVariant = 'default' | 'secondary' | 'destructive' | 'outline';

export const RUN_STATE_LABELS: Record<RunState, string> = {
  queued: 'Queued',
  running: 'Running',
  partial: 'Partly applied, resuming',
  succeeded: 'Succeeded',
  failed: 'Failed',
  canceled: 'Canceled',
};

const RUN_STATE_VARIANTS: Record<RunState, BadgeVariant> = {
  queued: 'outline',
  running: 'outline',
  partial: 'outline',
  succeeded: 'secondary',
  failed: 'destructive',
  canceled: 'outline',
};

export function runKindLabel(
  run: Pick<ConnectionRun, 'kind'> & { direction?: string | null },
): string {
  switch (run.kind) {
    case 'test':
      return run.direction === 'mmr_push'
        ? 'Test: MMR push health'
        : run.direction === 'promotion_push'
          ? 'Test: promotion push health'
          : 'Test: MMR pull';
    case 'mmr_pull':
      return 'MMR pull';
    case 'mmr_push':
      return 'MMR push';
    default:
      return 'Promotion push';
  }
}

export function RunStateBadge({
  state,
  testId,
}: {
  state: RunState;
  testId?: string;
}) {
  return (
    <Badge variant={RUN_STATE_VARIANTS[state]} data-testid={testId}>
      {RUN_STATE_LABELS[state]}
    </Badge>
  );
}

type CounterField =
  | 'request_count'
  | 'row_count'
  | 'updated_count'
  | 'unchanged_count'
  | 'unmatched_count'
  | 'invalid_count'
  | 'conflict_count'
  | 'skipped_policy_count'
  | 'missing_identifier_count'
  | 'verified_count';

const COUNTERS: { field: CounterField; label: string }[] = [
  { field: 'request_count', label: 'requests' },
  { field: 'row_count', label: 'rows' },
  { field: 'updated_count', label: 'updated' },
  { field: 'unchanged_count', label: 'unchanged' },
  { field: 'unmatched_count', label: 'unmatched' },
  { field: 'invalid_count', label: 'invalid' },
  { field: 'conflict_count', label: 'conflicts' },
  { field: 'skipped_policy_count', label: 'kept by overwrite rule' },
  { field: 'missing_identifier_count', label: 'missing IDs' },
  { field: 'verified_count', label: 'verified' },
];

/** Server counters as text; zeros after the first four are left out. */
export function RunCounters({
  run,
}: {
  run: Pick<RunSummary, CounterField | 'error_code'>;
}) {
  const shown = COUNTERS.filter(
    ({ field }, i) => i < 4 || Number(run[field]) > 0,
  );
  return (
    <ul
      className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground"
      data-testid="api-connection-run-counters"
    >
      {shown.map(({ field, label }) => (
        <li key={field}>
          <span className="font-medium text-foreground">{run[field]}</span>{' '}
          {label}
        </li>
      ))}
      {run.error_code && (
        <li className="text-destructive">
          {connectionErrorMessage(run.error_code)}
        </li>
      )}
    </ul>
  );
}

export interface MakeRunColumnsOptions {
  testIdPrefix: string;
  onView: (run: ConnectionRun) => void;
}

export function makeConnectionRunColumns({
  testIdPrefix,
  onView,
}: MakeRunColumnsOptions): AppColumnDef<ConnectionRun>[] {
  return [
    {
      id: 'created',
      accessorFn: (r) => new Date(r.created_at).getTime(),
      header: ({ column }) => (
        <DataTableColumnHeader column={column} title="Started" />
      ),
      cell: ({ row }) => {
        const r = row.original;
        return (
          <div className="flex min-w-0 flex-col gap-0.5">
            <span>{relativeTime(r.created_at)}</span>
            <span
              className="text-xs text-muted-foreground md:hidden"
              data-testid={`${testIdPrefix}-summary-${r.id}`}
            >
              {runKindLabel(r)} · {RUN_STATE_LABELS[r.state]} ·{' '}
              {r.updated_count} updated
            </span>
          </div>
        );
      },
    },
    {
      id: 'kind',
      header: 'Run',
      enableSorting: false,
      accessorFn: (r) => runKindLabel(r),
      cell: ({ row }) => (
        <span className="flex flex-col">
          <span>{runKindLabel(row.original)}</span>
          {row.original.health_only && (
            <span className="text-xs text-muted-foreground">
              Health check only
            </span>
          )}
        </span>
      ),
      meta: {
        headClassName: 'hidden md:table-cell',
        cellClassName: 'hidden md:table-cell',
      },
    },
    {
      id: 'state',
      header: 'Status',
      enableSorting: false,
      accessorFn: (r) => r.state,
      cell: ({ row }) => (
        <RunStateBadge
          state={row.original.state}
          testId={`${testIdPrefix}-state-${row.original.id}`}
        />
      ),
      meta: {
        headClassName: 'hidden w-36 md:table-cell',
        cellClassName: 'hidden w-36 md:table-cell',
      },
    },
    {
      id: 'counts',
      header: 'Result',
      enableSorting: false,
      accessorFn: (r) => r.updated_count,
      cell: ({ row }) => {
        const r = row.original;
        return (
          <span className="text-xs text-muted-foreground">
            {r.updated_count} updated, {r.unmatched_count} unmatched,{' '}
            {r.conflict_count} conflicts
            {r.error_code ? ` · ${connectionErrorMessage(r.error_code)}` : ''}
          </span>
        );
      },
      meta: {
        headClassName: 'hidden lg:table-cell',
        cellClassName: 'hidden lg:table-cell',
      },
    },
    {
      id: 'actions',
      header: () => <span className="sr-only">Actions</span>,
      enableSorting: false,
      cell: ({ row }) => (
        <SecondaryButton
          type="button"
          size="sm"
          className="min-h-11 sm:min-h-8"
          onClick={(e) => {
            e.stopPropagation();
            onView(row.original);
          }}
          aria-label={`View ${runKindLabel(row.original)} run from ${relativeTime(row.original.created_at)}`}
          data-testid={`${testIdPrefix}-view-${row.original.id}`}
        >
          View
        </SecondaryButton>
      ),
      meta: { headClassName: 'w-20', cellClassName: 'w-20' },
    },
  ];
}
